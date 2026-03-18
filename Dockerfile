FROM python:3.11-slim

WORKDIR /app

# Install speks package
COPY pyproject.toml setup.cfg* README.md ./
COPY speks/ speks/
RUN pip install --no-cache-dir .

# Copy the example project used for the live demo
ARG EXAMPLE_DIR=examples/credit-evaluation
COPY ${EXAMPLE_DIR}/ /project/

WORKDIR /project

# Point PlantUML to the companion container (or a public domain via PLANTUML_URL)
ARG PLANTUML_URL=http://plantuml:8080/plantuml
RUN sed -i '/^locale/a plantuml_server = "'"${PLANTUML_URL}"'"' speks.toml

EXPOSE 8000

CMD ["speks", "serve", "--port", "8000"]
