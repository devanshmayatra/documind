FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py sources.json ./
COPY core/ ./core/
COPY assets/ ./assets/
COPY .streamlit/config.toml ./.streamlit/config.toml
COPY data/sources/ ./data/sources/

EXPOSE 8501
CMD ["streamlit", "run", "app.py"]
