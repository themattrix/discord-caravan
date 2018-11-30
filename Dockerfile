FROM python:3.7

RUN python -m pip install pipenv==2018.11.26

WORKDIR /usr/src/app

COPY ./Pipfile* ./
RUN pipenv install

COPY ./caravan_bot ./caravan_bot

ENTRYPOINT ["pipenv", "run", "python", "-m", "caravan_bot", "--gyms", "/gyms.json"]
