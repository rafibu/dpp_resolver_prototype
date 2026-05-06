FROM python:3.14-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
COPY src/ src/

RUN uv pip install --system .

EXPOSE 8080

CMD ["uvicorn", "generic_dpp_platform.main:app", "--host", "0.0.0.0", "--port", "8080"]