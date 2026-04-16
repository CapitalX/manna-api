# SPDX-License-Identifier: AGPL-3.0-or-later
# Manna - A recipe management platform forked from Mealie
# Copyright (C) 2026 Manna Contributors

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
