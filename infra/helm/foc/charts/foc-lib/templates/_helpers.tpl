{{- define "foc-lib.labels" -}}
app.kubernetes.io/part-of: campus-errand
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{/* Prepend global.imageRegistry when set (empty locally, ghcr.io/<org> on EC2). */}}
{{- define "foc-lib.image" -}}
{{- $reg := .Values.global.imageRegistry | default "" -}}
{{- if $reg -}}{{ $reg }}/{{ end }}{{ .Values.image.repository }}:{{ .Values.image.tag | default "dev" }}
{{- end -}}

{{/* Cross-namespace service FQDN. Call with {svc, ns}. */}}
{{- define "foc-lib.fqdn" -}}
{{ .svc }}.{{ .ns }}.svc.cluster.local
{{- end -}}
