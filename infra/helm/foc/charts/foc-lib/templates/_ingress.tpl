{{- define "foc-lib.ingress" -}}
{{- $ing := .Values.ingress -}}
{{- if $ing.enabled -}}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ .Chart.Name }}
  namespace: {{ .Values.namespace }}
  labels:
    app.kubernetes.io/name: {{ .Chart.Name }}
    {{- include "foc-lib.labels" . | nindent 4 }}
  {{- if $ing.tls.enabled }}
  annotations:
    cert-manager.io/cluster-issuer: {{ $ing.tls.issuer }}
  {{- end }}
spec:
  ingressClassName: {{ $ing.className | default "traefik" }}
  {{- if $ing.tls.enabled }}
  tls:
    - hosts:
        - {{ $ing.host | quote }}
      secretName: {{ $ing.tls.secretName | default (printf "%s-tls" .Chart.Name) }}
  {{- end }}
  rules:
    - host: {{ $ing.host | quote }}
      http:
        paths:
          - path: {{ $ing.path | default "/" }}
            pathType: {{ $ing.pathType | default "Prefix" }}
            backend:
              service:
                name: {{ $ing.serviceName | default .Chart.Name }}
                port:
                  number: {{ $ing.servicePort | default .Values.port | default 8000 }}
{{- end -}}
{{- end -}}
