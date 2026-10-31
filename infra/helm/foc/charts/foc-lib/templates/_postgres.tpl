{{- define "foc-lib.postgres" -}}
{{- $pg := .Values.postgres -}}
apiVersion: v1
kind: Service
metadata:
  name: {{ $pg.name }}
  namespace: {{ .Values.namespace }}
  labels:
    app.kubernetes.io/name: {{ $pg.name }}
    {{- include "foc-lib.labels" . | nindent 4 }}
spec:
  clusterIP: None
  selector:
    app.kubernetes.io/name: {{ $pg.name }}
  ports:
    - name: postgres
      port: 5432
      targetPort: 5432
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: {{ $pg.name }}
  namespace: {{ .Values.namespace }}
  labels:
    app.kubernetes.io/name: {{ $pg.name }}
    {{- include "foc-lib.labels" . | nindent 4 }}
  annotations:
    argocd.argoproj.io/sync-options: Delete=false,Prune=false
spec:
  serviceName: {{ $pg.name }}
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: {{ $pg.name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {{ $pg.name }}
    spec:
      containers:
        - name: postgres
          image: {{ $pg.image | default "postgres:16-alpine" }}
          args:
            - "-c"
            - "shared_buffers={{ $pg.sharedBuffers | default "128MB" }}"
            - "-c"
            - "max_connections={{ $pg.maxConnections | default 50 }}"
          ports:
            - containerPort: 5432
          env:
            - name: POSTGRES_DB
              value: {{ $pg.dbName | quote }}
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef:
                  name: {{ $pg.secret }}
                  key: POSTGRES_USER
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ $pg.secret }}
                  key: POSTGRES_PASSWORD
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata
          readinessProbe:
            exec:
              command: ["sh", "-c", "pg_isready -U \"$POSTGRES_USER\" -d {{ $pg.dbName }}"]
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 6
          livenessProbe:
            exec:
              command: ["sh", "-c", "pg_isready -U \"$POSTGRES_USER\" -d {{ $pg.dbName }}"]
            initialDelaySeconds: 20
            periodSeconds: 20
          resources:
            {{- toYaml $pg.resources | nindent 12 }}
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: {{ $pg.storageClass | default "local-path" }}
        resources:
          requests:
            storage: {{ $pg.storage | default "1Gi" }}
{{- end -}}
