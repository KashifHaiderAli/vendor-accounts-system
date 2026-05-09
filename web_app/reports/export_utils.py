from __future__ import annotations

import csv

from django.http import HttpResponse


def csv_response(filename, columns, rows):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow([column["label"] for column in columns])
    for row in rows:
        writer.writerow([row.get(column["key"], "") for column in columns])
    return response
