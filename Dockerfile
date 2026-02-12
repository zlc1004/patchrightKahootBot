FROM python:3.12-bookworm

ENV PYTHONDONTWRITEBYTECODE=1

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    python -m pip install -r requirements.txt

RUN patchright install --with-deps

RUN apt update -y && apt install xauth x11vnc -y

COPY . .

RUN chmod +x /app/entry.sh

ENTRYPOINT [ "/app/entry.sh" ]