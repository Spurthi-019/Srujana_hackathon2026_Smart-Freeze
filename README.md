# Smart Freeze

A hackathon prototype for banks: after a scam, trace stolen money across accounts, score investigation priority, and recommend the smallest effective action (lien / lien+cap / timed hold). SIMULATED data only.

## Running the Application

### 1. Run the Backend API
```bash
uvicorn api.main:app --port 8000
```

### 2. Run the React UI
```bash
cd frontend
npm install
npm run dev
```
Then open http://localhost:5173.
