{{- define "foc-lib.backupCronjob" -}}
{{- $b := .Values.global.backup -}}
{{- if and $b $b.enabled -}}
{{- $reg := .Values.global.imageRegistry | default "" -}}
apiVersion: batch/v1
kind: CronJob
metadata:
  name: {{ .Values.postgres.name }}-backup
  namespace: {{ .Values.namespace }}
  labels:
    app.kubernetes.io/name: {{ .Values.postgres.name }}-backup
    {{- include "foc-lib.labels" . | nindent 4 }}
spec:
  schedule: {{ $b.schedule | default "30 1 * * *" | quote }}
  {{- with $b.timeZone }}
  timeZone: {{ . | quote }}
  {{- end }}
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          restartPolicy: Never
          {{- include "foc-lib.imagePullSecrets" . | nindent 10 }}
          containers:
            - name: backup
              image: {{ if $reg }}{{ $reg }}/{{ end }}{{ $b.image.repository }}:{{ $b.image.tag | default "dev" }}
              imagePullPolicy: {{ .Values.global.imagePullPolicy | default "IfNotPresent" }}
              env:
                - name: DATABASE_URL
                  valueFrom:
                    secretKeyRef:
                      name: {{ .Values.postgres.secret }}
                      key: DATABASE_URL
                - name: DB_NAME
                  value: {{ .Values.postgres.dbName | quote }}
                - name: S3_BUCKET
                  value: {{ $b.bucket | quote }}
                - name: AWS_DEFAULT_REGION
                  value: {{ $b.region | default "ap-southeast-1" | quote }}
                - name: S3_ENDPOINT_URL
                  value: {{ $b.s3EndpointUrl | default "" | quote }}
                {{- with $b.staticCredentialsSecret }}
                - name: AWS_ACCESS_KEY_ID
                  valueFrom:
                    secretKeyRef:
                      name: {{ . }}
                      key: AWS_ACCESS_KEY_ID
                - name: AWS_SECRET_ACCESS_KEY
                  valueFrom:
                    secretKeyRef:
                      name: {{ . }}
                      key: AWS_SECRET_ACCESS_KEY
                {{- end }}
              resources:
                requests:
                  cpu: 25m
                  memory: 64Mi
                limits:
                  cpu: 250m
                  memory: 128Mi
{{- end -}}
{{- end -}}
