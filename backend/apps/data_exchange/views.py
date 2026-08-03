import csv
import io

from django.http import HttpResponse
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


MAX_ROWS = 10_000
MAX_COLUMNS = 100
MAX_CELL_LENGTH = 20_000


class CsvExportSerializer(serializers.Serializer):
    filename = serializers.RegexField(r"^[\w.-]{1,100}$", default="export.csv")
    columns = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        max_length=MAX_COLUMNS,
    )
    rows = serializers.ListField(
        child=serializers.DictField(),
        max_length=MAX_ROWS,
    )

    def validate_columns(self, columns):
        cleaned = []
        seen = set()
        for column in columns:
            key = str(column.get("key", "")).strip()
            label = str(column.get("label", key)).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            cleaned.append({"key": key, "label": label[:200]})
        if not cleaned:
            raise serializers.ValidationError("Informe ao menos uma coluna válida.")
        return cleaned


class CsvExportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CsvExportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow([column["label"] for column in data["columns"]])
        for row in data["rows"]:
            writer.writerow([
                self._cell(row.get(column["key"]))
                for column in data["columns"]
            ])
        response = HttpResponse(stream.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{data["filename"]}"'
        return response

    @staticmethod
    def _cell(value):
        if isinstance(value, (list, tuple, set)):
            value = " | ".join(map(str, value))
        elif isinstance(value, dict):
            value = str(value)
        value = str(value if value is not None else "")[:MAX_CELL_LENGTH]
        # Prevent formulas from being executed when the CSV is opened in Excel/Sheets.
        if value.startswith(("=", "+", "-", "@")):
            value = f"'{value}"
        return value


class CsvParseView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"detail": "Envie um arquivo CSV."}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size > 5 * 1024 * 1024:
            return Response({"detail": "O CSV deve ter no máximo 5 MB."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            text = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return Response({"detail": "Use um CSV em UTF-8."}, status=status.HTTP_400_BAD_REQUEST)
        reader = csv.DictReader(io.StringIO(text))
        headers = [str(header or "").strip() for header in (reader.fieldnames or [])]
        if not headers or len(headers) > MAX_COLUMNS:
            return Response({"detail": "Cabeçalho CSV inválido."}, status=status.HTTP_400_BAD_REQUEST)
        rows = []
        for index, row in enumerate(reader):
            if index >= MAX_ROWS:
                return Response({"detail": f"Limite de {MAX_ROWS} linhas excedido."}, status=status.HTTP_400_BAD_REQUEST)
            rows.append({
                header: str(row.get(raw_header, "") or "")[:MAX_CELL_LENGTH]
                for header, raw_header in zip(headers, reader.fieldnames)
            })
        return Response({"headers": headers, "rows": rows, "count": len(rows)})
