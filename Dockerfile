FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
RUN useradd -u 10001 -m appuser
COPY requirements.txt .
# Optional build-only CA bundle for managed development/CI proxies; never copied into the image.
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then \
      PIP_CERT=/run/secrets/build_ca pip install --no-cache-dir -r requirements.txt; \
    else pip install --no-cache-dir -r requirements.txt; fi
COPY app ./app
RUN python -m compileall -q /srv/app && chmod -R a+rX /srv/app
RUN mkdir -p /data && chown appuser:appuser /data
USER appuser
EXPOSE 8080
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080","--proxy-headers","--forwarded-allow-ips","127.0.0.1"]
