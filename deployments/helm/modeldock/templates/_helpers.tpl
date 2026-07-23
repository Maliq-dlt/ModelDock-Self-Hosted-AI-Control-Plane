{{- define "modeldock.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "modeldock.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "modeldock.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "modeldock.labels" -}}
app.kubernetes.io/name: {{ include "modeldock.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "modeldock.secretName" -}}
{{- if .Values.secrets.create }}{{ include "modeldock.fullname" . }}-secrets{{ else }}{{ .Values.secrets.existingSecret }}{{ end }}
{{- end }}