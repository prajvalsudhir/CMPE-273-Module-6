# Inventory Service on Kubernetes

Inventory Service with 2 replicas, exposed by a Service, with 1 client
that requests it by Service name.

## Architecture

![Architecture block diagram](diagrams/architecture.svg)

The client requests `http://inventory`. The Service named `inventory`
forwards to the ready Inventory Pods. The client never uses Pod addresses.

## Deploying

Start Docker Desktop, then:

```bash
brew install minikube kubectl
minikube start --driver=docker
DOCKER_BUILDKIT=0 docker build -t inventory:local .
DOCKER_BUILDKIT=0 docker build -t client:local -f Dockerfile.client .
minikube image load inventory:local
minikube image load client:local
kubectl apply -f k8s/
kubectl wait --for=condition=ready pod -l app=inventory --timeout=120s
```

The Inventory app serves `/` and `/ready`. `/ready` returns 500 when
`/tmp/unready` exists in that Pod, so readiness can be failed without
stopping the Pod.

## Evidence: both replicas receiving requests

Commands used:

```bash
kubectl get pods -o wide
kubectl get svc inventory
kubectl get endpoints inventory
kubectl logs deployment/client --tail=40
```

Excerpts from that output. Both Running Inventory Pods are in the
endpoints, and both appear in client logs.

```
inventory-6998dd9945-kww4z   1/1     Running       0          17s   10.244.0.8   minikube
inventory-6998dd9945-zjh5x   1/1     Running       0          17s   10.244.0.7   minikube
inventory   ClusterIP   10.110.115.98   <none>        80/TCP    20m
inventory   10.244.0.7:8080,10.244.0.8:8080
[client] request 5 -> served by inventory-6998dd9945-kww4z
[client] request 6 -> served by inventory-6998dd9945-zjh5x
[client] request 7 -> served by inventory-6998dd9945-kww4z
[client] request 9 -> served by inventory-6998dd9945-zjh5x
```

![Both replicas](screenshots/both-replicas.png)

## Evidence: readiness failure

Commands used (`$POD` was `inventory-6998dd9945-crj96`):

```bash
POD=$(kubectl get pods -l app=inventory --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
kubectl get pods -l app=inventory
kubectl exec "$POD" -- touch /tmp/unready
# wait 20s for the readiness probe to fail
kubectl get pods -l app=inventory
kubectl get endpoints inventory
kubectl logs deployment/client --tail=15
```

The Pod stayed Running but went to 0/1, the endpoints listed only
the other Pod, and subsequent client requests went only to that Pod.

```
inventory-6998dd9945-crj96   0/1     Running   0          8m48s
inventory-6998dd9945-zjh5x   1/1     Running   0          9m31s
inventory   10.244.0.7:8080
[client] request 545 -> served by inventory-6998dd9945-zjh5x
[client] request 546 -> served by inventory-6998dd9945-zjh5x
[client] request 547 -> served by inventory-6998dd9945-zjh5x
[client] request 548 -> served by inventory-6998dd9945-zjh5x
```

![Readiness failure](screenshots/readiness-failure.png)

## Evidence: readiness recovery

Commands used (same `$POD` as above):

```bash
kubectl exec "$POD" -- rm /tmp/unready
# wait 20s for the readiness probe to pass again
kubectl get pods -l app=inventory
kubectl get endpoints inventory
kubectl logs deployment/client --tail=15
```

The Pod returned to 1/1, both Pods were in the endpoints again, and
the restored Pod served again.

```
inventory-6998dd9945-crj96   1/1     Running   0          9m8s
inventory-6998dd9945-zjh5x   1/1     Running   0          9m51s
inventory   10.244.0.10:8080,10.244.0.7:8080
[client] request 564 -> served by inventory-6998dd9945-crj96
[client] request 566 -> served by inventory-6998dd9945-crj96
[client] request 568 -> served by inventory-6998dd9945-zjh5x
```

![Readiness recovery](screenshots/readiness-recovery.png)

## Evidence: Pod deletion and replacement

Commands used (`$OLD` was `inventory-6998dd9945-kww4z`):

```bash
OLD=$(kubectl get pods -l app=inventory -o jsonpath='{.items[0].metadata.name}')
kubectl get svc inventory
kubectl delete pod "$OLD"
kubectl wait --for=condition=ready pod -l app=inventory --timeout=120s
kubectl get pods
kubectl get svc inventory
kubectl get endpoints inventory
kubectl logs deployment/client --tail=30
```

Kubernetes created `inventory-6998dd9945-crj96` with a different
name. The Service name and ClusterIP were unchanged, and the client
kept succeeding through the Service, with the new Pod serving.

```
Deleting pod: inventory-6998dd9945-kww4z
inventory   ClusterIP   10.110.115.98   <none>        80/TCP    20m
inventory-6998dd9945-crj96   1/1     Running   0          37s
inventory-6998dd9945-zjh5x   1/1     Running   0          80s
inventory   ClusterIP   10.110.115.98   <none>        80/TCP    21m
inventory   10.244.0.10:8080,10.244.0.7:8080
[client] request 47 -> served by inventory-6998dd9945-crj96
[client] request 48 -> served by inventory-6998dd9945-zjh5x
[client] request 49 -> served by inventory-6998dd9945-crj96
```

![Pod deletion and replacement](screenshots/pod-deletion.png)

### Continuous client log spanning Pod deletion

A second deletion was run with the client log followed across it,
so one log shows requests before, during, and after the deletion,
with no tail-only gap. Commands used (`$OLD` was
`inventory-6998dd9945-crj96`):

```bash
OLD=$(kubectl get pods -l app=inventory --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
kubectl logs -f deployment/client > evidence/deletion-continuous-log.txt &
# sleep 10s, then
kubectl delete pod "$OLD"
kubectl wait --for=condition=ready pod -l app=inventory --timeout=120s
# sleep 10s, then stop the log follow
kubectl get pods -l app=inventory
kubectl get svc inventory
kubectl get endpoints inventory
```

`crj96` was deleted and `fxrr4` replaced it, with the Service name
and ClusterIP unchanged. In the continuous log, requests 108–112
were served by the old Pods, request 113 was the first served by
`fxrr4`, and requests after that alternate between `fxrr4` and
`zjh5x` — consecutive request numbers, no error at the transition.
Note: this client Pod had restarted with minikube, so its first 9
requests failed DNS while the cluster came back up; from request 10
onward it served continuously, including across this deletion.

```
inventory-6998dd9945-crj96   1/1     Running   1 (2m8s ago)   14h
inventory-6998dd9945-zjh5x   1/1     Running   1 (2m8s ago)   14h
inventory   ClusterIP   10.110.115.98   <none>        80/TCP    14h
inventory   10.244.0.3:8080,10.244.0.4:8080
Deleting pod: inventory-6998dd9945-crj96
inventory-6998dd9945-fxrr4   1/1     Running   0            42s
inventory-6998dd9945-zjh5x   1/1     Running   1 (3m ago)   14h
inventory   ClusterIP   10.110.115.98   <none>        80/TCP    14h
inventory   10.244.0.4:8080,10.244.0.6:8080
[client] request 108 -> served by inventory-6998dd9945-crj96
[client] request 109 -> served by inventory-6998dd9945-zjh5x
[client] request 110 -> served by inventory-6998dd9945-zjh5x
[client] request 111 -> served by inventory-6998dd9945-zjh5x
[client] request 112 -> served by inventory-6998dd9945-zjh5x
[client] request 113 -> served by inventory-6998dd9945-fxrr4
[client] request 114 -> served by inventory-6998dd9945-zjh5x
[client] request 115 -> served by inventory-6998dd9945-zjh5x
[client] request 116 -> served by inventory-6998dd9945-fxrr4
[client] request 117 -> served by inventory-6998dd9945-zjh5x
[client] request 118 -> served by inventory-6998dd9945-fxrr4
[client] request 119 -> served by inventory-6998dd9945-fxrr4
[client] request 120 -> served by inventory-6998dd9945-fxrr4
```

![Continuous client log spanning Pod deletion](screenshots/pod-deletion-continuous.png)

## Why is a stable Service name useful when Pods can fail or be replaced?

A stable Service name is useful because Pods are not stable. They can
fail readiness, be deleted, or be replaced with new names and new IP
addresses, as shown above. The client does not need to track those
changes, because it always requests the same Service name and
Kubernetes forwards to whichever Pods are currently ready. That keeps
the client working through a Pod failure without any change to the
client itself, and it lets the system scale or replace Pods without
updating callers.

