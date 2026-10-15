FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir 'oss2>=2.19,<3' 'Pillow>=11,<13' 'requests>=2.32,<3'
COPY diary_presets /app/diary_presets
COPY deployment/preset-processor/worker.py /app/worker.py
CMD ["python", "worker.py"]
