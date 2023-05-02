FROM python:3.10.11-slim-buster
ARG PIP_NO_CACHE_DIR=1
COPY . /app
WORKDIR /app
RUN apt update && apt install -y ffmpeg
# RUN apt install -y ffmpeg
RUN pip install -r requirements.txt
EXPOSE 5000
ENTRYPOINT [ "python" ]
CMD [ "app.py" ]