FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update \
	&& apt-get upgrade -y \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
	&& python -m pip install --no-cache-dir --upgrade --force-reinstall -r /app/requirements.txt \
	&& python -m pip check

COPY src/app/ /app/

CMD ["python", "main.py"]

