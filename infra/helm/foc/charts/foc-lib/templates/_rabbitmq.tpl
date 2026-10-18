{{- define "foc-lib.rabbitmq" -}}
apiVersion: v1
kind: Service
metadata:
  name: rabbitmq
  namespace: {{ .Values.namespace }}
  labels:
    app.kubernetes.io/name: rabbitmq
    {{- include "foc-lib.labels" . | nindent 4 }}
spec:
  selector:
    app.kubernetes.io/name: rabbitmq
  ports:
    - name: amqp
      port: 5672
      targetPort: 5672
    - name: management
      port: 15672
      targetPort: 15672
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: rabbitmq
  namespace: {{ .Values.namespace }}
  labels:
    app.kubernetes.io/name: rabbitmq
    {{- include "foc-lib.labels" . | nindent 4 }}
spec:
  serviceName: rabbitmq
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: rabbitmq
  template:
    metadata:
      labels:
        app.kubernetes.io/name: rabbitmq
    spec:
      containers:
        - name: rabbitmq
          image: {{ .Values.image | default "rabbitmq:3.13-management-alpine" }}
          ports:
            - containerPort: 5672
            - containerPort: 15672
          env:
            - name: RABBITMQ_DEFAULT_USER
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.secret }}
                  key: RABBITMQ_DEFAULT_USER
            - name: RABBITMQ_DEFAULT_PASS
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.secret }}
                  key: RABBITMQ_DEFAULT_PASS
          readinessProbe:
            exec:
              command: ["rabbitmq-diagnostics", "-q", "ping"]
            initialDelaySeconds: 15
            periodSeconds: 15
            failureThreshold: 6
          livenessProbe:
            exec:
              command: ["rabbitmq-diagnostics", "-q", "ping"]
            initialDelaySeconds: 40
            periodSeconds: 30
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          volumeMounts:
            - name: data
              mountPath: /var/lib/rabbitmq
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: {{ .Values.storageClass | default "local-path" }}
        resources:
          requests:
            storage: {{ .Values.storage | default "1Gi" }}
{{- end -}}
