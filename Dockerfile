FROM python:3.11.9-slim-bullseye

WORKDIR /src

COPY requirements.txt requirements.txt

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -Ur requirements.txt
#COPY --from=base /usr/local/lib/python3.10/site-packages/ /usr/local/lib/python3.10/site-packages/

COPY . .

RUN mkdir ./images
RUN pip install — no-cache-dir -r requirements.txt

CMD ["python", "-u", "./main.py"]
