# Production Deployment Guide

Follow these step-by-step instructions to get the Adjacency Research Engine running online.

---

## Step 1: Push Codebase to GitHub

1. Initialize git and commit your current files (including the populated SQLite database `backend/breakthrough_radar.db` since it serves as the precomputed cache):
   ```bash
   git init
   git add .
   git commit -m "feat: complete prompt engineered backend and caching layer"
   ```
2. Create a new public/private repository on [GitHub](https://github.com).
3. Link your local repository and push:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
   git branch -M main
   git push -u origin main
   ```

---

## Step 2: Deploy the Backend (Python / Flask)

Since you have a pre-configured `Dockerfile.backend`, you can easily deploy the backend using any container hosting service.

### Option A: Render.com (Recommended Free Tier)
1. Sign up on [Render](https://render.com).
2. Click **New** -> **Web Service**.
3. Connect your GitHub repository.
4. Set the following configuration:
   - **Name**: `adjacency-backend`
   - **Environment**: `Docker`
   - **Docker Path**: `Dockerfile.backend`
   - **Branch**: `main`
5. Under **Environment Variables**, add:
   - `GROQ_API_KEY` = `your_groq_api_key`
   - `GEMINI_API_KEY` = `your_gemini_api_key`
6. Click **Deploy Web Service**. Once deployed, Render will provide a public URL (e.g. `https://adjacency-backend.onrender.com`).

---

## Step 3: Deploy the Frontend (Next.js) to Vercel

1. Sign up on [Vercel](https://vercel.com).
2. Click **Add New** -> **Project**.
3. Connect your GitHub repository.
4. Select the project root, and customize settings:
   - **Framework Preset**: `Next.js`
   - **Root Directory**: `frontend`
5. Under **Environment Variables**, add:
   - `NEXT_PUBLIC_API_URL` = `https://adjacency-backend.onrender.com` (use your Render Web Service URL from Step 2)
6. Click **Deploy**. Vercel will build and launch your application online!
