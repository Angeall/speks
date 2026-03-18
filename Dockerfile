FROM python:3.11-slim

WORKDIR /app

# Install speks package
COPY pyproject.toml setup.cfg* README.md ./
COPY speks/ speks/
RUN pip install --no-cache-dir .

# Copy the example project used for the live demo
COPY examples/credit-evaluation/ /project/

WORKDIR /project

# Point PlantUML to the companion container
RUN sed -i '/^locale/a plantuml_server = "http://plantuml:8080/plantuml"' speks.toml

EXPOSE 8000

CMD ["speks", "serve", "--port", "8000"]
