FROM python:3.10-slim

# Hugging Face Spaces requires running as a non-root user
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Install dependencies
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY --chown=user . .

# Hugging Face Spaces expose port 7860
EXPOSE 7860

# Run Simulator in background and FastAPI in foreground
CMD python simulator.py & uvicorn main:app --host 0.0.0.0 --port 7860
