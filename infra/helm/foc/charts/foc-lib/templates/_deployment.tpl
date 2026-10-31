{{- define "foc-lib.deployment" -}}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Chart.Name }}
  namespace: {{ .Values.namespace }}
  labels:
    app.kubernetes.io/name: {{ .Chart.Name }}
    {{- include "foc-lib.labels" . | nindent 4 }}
spec:
  {{- if not (and .Values.hpa .Values.hpa.enabled) }}
  replicas: {{ .Values.replicas | default 1 }}
  {{- end }}
  selector:
    matchLabels:
      app.kubernetes.io/name: {{ .Chart.Name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {{ .Chart.Name }}
    spec:
      {{- include "foc-lib.imagePullSecrets" . | nindent 6 }}
      containers:
        - name: {{ .Chart.Name }}
          image: {{ include "foc-lib.image" . }}
          imagePullPolicy: {{ .Values.global.imagePullPolicy | default "IfNotPresent" }}
          ports:
            - containerPort: {{ .Values.port | default 8000 }}
          env:
            {{- range $k, $v := .Values.env }}
            - name: {{ $k }}
              value: {{ $v | quote }}
            {{- end }}
            {{- range .Values.secretEnv }}
            - name: {{ .name }}
              valueFrom:
                secretKeyRef:
                  name: {{ .secret }}
                  key: {{ .key }}
            {{- end }}
          readinessProbe:
            httpGet:
              path: {{ .Values.healthPath | default "/health" }}
              port: {{ .Values.port | default 8000 }}
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 6
          livenessProbe:
            httpGet:
              path: {{ .Values.healthPath | default "/health" }}
              port: {{ .Values.port | default 8000 }}
            initialDelaySeconds: 20
            periodSeconds: 20
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
{{- end -}}
