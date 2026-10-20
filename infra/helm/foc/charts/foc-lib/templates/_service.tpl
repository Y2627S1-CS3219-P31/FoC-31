{{- define "foc-lib.service" -}}
apiVersion: v1
kind: Service
metadata:
  name: {{ .Chart.Name }}
  namespace: {{ .Values.namespace }}
  labels:
    app.kubernetes.io/name: {{ .Chart.Name }}
    {{- include "foc-lib.labels" . | nindent 4 }}
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: {{ .Chart.Name }}
  ports:
    - name: http
      port: {{ .Values.port | default 8000 }}
      targetPort: {{ .Values.port | default 8000 }}
{{- end -}}
