FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
COPY backup.py ./

RUN pip install --no-cache-dir requests APScheduler

ENV TZ=Asia/Taipei
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

CMD ["python", "backup.py"]
