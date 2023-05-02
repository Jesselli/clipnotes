FROM python:3.10.11-slim-buster
COPY . /app
WORKDIR /app
RUN apt update
RUN apt install -y ffmpeg
RUN pip install -r requirements.txt
EXPOSE 5000
ENTRYPOINT [ "python" ]
CMD [ "app.py" ]