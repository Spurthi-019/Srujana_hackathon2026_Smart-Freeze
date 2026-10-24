# Smart Freeze: agent rules
Prototype for banks: after a scam, trace stolen money across accounts, score how mule-like each account is, and recommend the smallest effective action (lien / lien+cap / timed hold). SIMULATED data only. Solo hackathon build.

Engines:
1. Tracing: 3 methods (proportional, FIFO, LIBR). min/max across methods = "sure part" and "ceiling".
2. Mule score S = f(B,T,H): B behaviour, T trail (uses tracing output), H history/legitimacy. Call it "investigation priority", never "probability of guilt".
3. Decision: low S -> lien on min; medium S -> lien on min+(max-min)*S plus cap; high S -> timed hold. Harm model + lambda slider trade recovery vs harm.

Rules:
- Edit only files named in the task. No refactors.
- Do not change names or columns in docs/CONTRACT.md without asking me.
- Python 3.11; pandas, numpy, networkx, scikit-learn, streamlit, plotly, pytest only.
- Simple readable code; interpretable models (logistic regression).
- Each module gets a pytest test; run it before saying done.
- Seed 42. Label all data "simulated". No real data or keys.
- Small commits. Never push unless I ask.
