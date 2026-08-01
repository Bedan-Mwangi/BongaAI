FROM node:18-bullseye
RUN apt-get update && apt-get install -y python3 python3-pip && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package.json ./
RUN npm install
COPY requirements.txt ./
RUN pip3 install -r requirements.txt --break-system-packages
COPY . .
RUN chmod +x start.sh
ENV PORT=10000
EXPOSE 10000
CMD ["./start.sh"]
