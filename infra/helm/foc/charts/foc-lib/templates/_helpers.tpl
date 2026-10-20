{{- define "foc-lib.labels" -}}
app.kubernetes.io/part-of: campus-errand
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{- define "foc-lib.image" -}}
{{- $reg := .Values.global.imageRegistry | default "" -}}
{{- if $reg -}}{{ $reg }}/{{ end }}{{ .Values.image.repository }}:{{ .Values.image.tag | default "dev" }}
{{- end -}}

{{- define "foc-lib.fqdn" -}}
{{ .svc }}.{{ .ns }}.svc.cluster.local
{{- end -}}
