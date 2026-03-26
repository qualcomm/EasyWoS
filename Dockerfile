# Stage 1: Build the frontend
FROM node:18-alpine AS frontend-builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY public/ public/
COPY web/ web/
# this will generate the production build in the /app/dist folder
RUN npm run build

# Stage 2: Build Python dependencies (Wheels)
FROM python:3.10 AS backend-builder

# Install compile-time dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirement.txt .
# Build wheels for all dependencies to avoid installing compilers in the final image
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirement.txt -i https://pypi.tuna.tsinghua.edu.cn/simple


# Stage 3: Final Runtime Image
# Use slim image to reduce size
FROM python:3.10-slim

# Install runtime system dependencies
# libmagic1: for python-magic
# git: for git repository scanning features
# sqlite3: for database management
RUN apt-get update && apt-get install -y \
    libmagic1 \
    sqlite3 \
    git \
    vim \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies from wheels
COPY --from=backend-builder /app/wheels /tmp/wheels
RUN pip install --no-cache-dir /tmp/wheels/* && rm -rf /tmp/wheels

# Copy backend application code
COPY app/ app/
COPY easywos/ easywos/
COPY helper/ helper/
COPY models/ models/
COPY scanner/ scanner/
COPY templates/ templates/
COPY util/ util/
COPY main.py settings.py init_user ./

# Copy built frontend assets from the builder stage
COPY --from=frontend-builder /app/dist ./dist

# Create directory for uploads/workspaces if needed
RUN mkdir -p /app/workspace

# Expose the port the app runs on
EXPOSE 8881

# Command to run the application
CMD ["python", "main.py"]
