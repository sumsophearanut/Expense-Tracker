"""Categories, demo data, auto-categorizer, forecast and anomaly detection."""
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline

MERCHANTS = {
    "Food & Dining": ["starbucks", "mcdonalds", "kfc", "pizza hut", "local restaurant", "subway", "cafe latte", "street food"],
    "Groceries": ["walmart", "lotus supermarket", "fresh market", "costco", "tesco", "grocery store"],
    "Transport": ["uber", "grab ride", "taxi", "shell fuel", "petrol station", "bus pass", "metro card", "tuk tuk"],
    "Shopping": ["amazon", "zara", "h&m", "ikea", "lazada", "shopee", "uniqlo"],
    "Bills & Utilities": ["electricity bill", "water bill", "internet provider", "phone plan", "rent payment"],
    "Entertainment": ["netflix", "spotify", "cinema tickets", "steam games", "concert tickets"],
    "Health": ["pharmacy", "clinic visit", "dentist", "gym membership", "hospital"],
    "Education": ["tuition fee", "university", "online course", "textbook", "stationery shop", "udemy"],
}
EXPENSE_CATEGORIES = list(MERCHANTS) + ["Other"]
INCOME_CATEGORIES = ["Salary", "Sales", "Allowance", "Freelance", "Gift", "Other income"]
USER_TYPES = ["Seller", "Student", "Young Adult"]
CURRENCIES = ["$", "៛", "€", "£", "¥", "฿"]

TYPICAL = {"Food & Dining": 6, "Groceries": 30, "Transport": 5, "Shopping": 40, "Bills & Utilities": 45,
           "Entertainment": 10, "Health": 25, "Education": 40}
FREQ = {"Food & Dining": 20, "Groceries": 6, "Transport": 14, "Shopping": 3, "Bills & Utilities": 3,
        "Entertainment": 3, "Health": 2, "Education": 1}


def make_demo_transactions(user_type="Young Adult", months=6, seed=11):
    rng = np.random.default_rng(seed)
    end = pd.Timestamp.today().normalize()
    start = (end - pd.DateOffset(months=months - 1)).replace(day=1)
    rows = []

    def add(d, t, cat, desc, amt):
        rows.append({"date": d, "type": t, "category": cat, "description": desc, "amount": round(float(amt), 2)})

    for m_start in pd.date_range(start, end, freq="MS"):
        days = pd.date_range(m_start, min(m_start + pd.offsets.MonthEnd(0), end))
        if user_type == "Seller":
            for _ in range(int(rng.integers(8, 14))):
                add(rng.choice(days), "Income", "Sales", f"Customer order #{rng.integers(100, 999)}", rng.uniform(40, 200))
        elif user_type == "Student":
            add(m_start, "Income", "Allowance", "Monthly allowance", 300)
            add(rng.choice(days), "Income", "Freelance", "Part-time job", rng.uniform(80, 160))
        else:
            add(m_start, "Income", "Salary", "Monthly salary", 1100)
        for cat in MERCHANTS:
            for _ in range(rng.poisson(FREQ[cat])):
                amt = TYPICAL[cat] * rng.lognormal(0, 0.4)
                if rng.random() < 0.012:
                    amt *= rng.uniform(5, 8)
                name = rng.choice(MERCHANTS[cat]).title()
                add(rng.choice(days), "Expense", cat, f"{name} #{rng.integers(100, 999)}", amt)
    return pd.DataFrame(rows)


def train_categorizer():
    rng = np.random.default_rng(0)
    X, y = [], []
    for cat, names in MERCHANTS.items():
        for n in names:
            for _ in range(12):
                X.append(f"{n} {rng.integers(100, 999)}")
                y.append(cat)
    return make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4)),
                         LogisticRegression(max_iter=1000)).fit(X, y)


def categorize(model, descriptions):
    descriptions = [str(d) for d in descriptions]
    if not descriptions:
        return []
    proba = model.predict_proba(descriptions)
    labels = model.classes_[proba.argmax(1)]
    return [str(l) if p.max() >= 0.25 else "Other" for l, p in zip(labels, proba)]


def monthly_by_category(expenses):
    d = expenses.copy()
    d["month"] = d["date"].dt.to_period("M").dt.to_timestamp()
    return d.pivot_table(index="month", columns="category", values="amount", aggfunc="sum", fill_value=0)


def forecast_next_month(expenses):
    """Linear trend over last 6 full months, blended with their mean."""
    if expenses.empty:
        return pd.Series(dtype=float)
    pv = monthly_by_category(expenses)
    cur = pd.Timestamp.today().to_period("M").to_timestamp()
    pv = pv[pv.index < cur].tail(6)
    out = {}
    for cat in pv.columns:
        y = pv[cat].values
        if len(y) >= 3:
            slope, icpt = np.polyfit(np.arange(len(y)), y, 1)
            pred = 0.5 * (slope * len(y) + icpt) + 0.5 * y.mean()
        else:
            pred = y.mean()
        out[cat] = max(float(pred), 0.0)
    return pd.Series(out).sort_values(ascending=False)


def detect_anomalies(expenses, threshold=3.5):
    d = expenses.copy()
    if d.empty:
        return d.assign(anomaly_score=[])

    def score(s):
        med = s.median()
        mad = (s - med).abs().median() or 1e-9
        return 0.6745 * (s - med) / mad
    d["anomaly_score"] = d.groupby("category")["amount"].transform(score)
    return d[d["anomaly_score"] > threshold].sort_values("anomaly_score", ascending=False)

# ------------------------------------------------------------ train model
MODEL_DIR = "models"


def model_path(user_id):
    return os.path.join(MODEL_DIR, f"categorizer_{user_id}.joblib")


def _builtin_samples(seed=0):
    rng = np.random.default_rng(seed)
    X, y = [], []
    for cat, names in MERCHANTS.items():
        for n in names:
            for _ in range(12):
                X.append(f"{n} {rng.integers(100, 999)}")
                y.append(cat)
    return X, y


def _make_pipeline(C=1.0):
    return make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4)),
                         LogisticRegression(max_iter=1000, C=C))


def train_and_evaluate(expenses, test_size=0.2, C=1.0, seed=42):
    """Train on built-in merchants + the user's labelled expenses.
    Returns (final_model, metrics dict, per-category report DataFrame)."""
    bx, by = _builtin_samples()
    u = expenses[(expenses["category"] != "Other") & expenses["description"].fillna("").str.strip().ne("")]
    ux, uy = u["description"].astype(str).tolist(), u["category"].tolist()

    def split(X, y):
        try:
            return train_test_split(X, y, test_size=test_size, random_state=seed, stratify=y)
        except ValueError:
            return train_test_split(X, y, test_size=test_size, random_state=seed)

    if len(ux) >= 20:  # enough personal data: test only on the user's own held-out rows
        Xtr, Xte, ytr, yte = split(ux, uy)
        X_train, y_train = bx + Xtr, by + ytr
        eval_on = "your transactions (held-out)"
    else:
        X_train, Xte, y_train, yte = split(bx + ux, by + uy)
        eval_on = "built-in sample (optimistic, add more of your own data)"

    pred = _make_pipeline(C).fit(X_train, y_train).predict(Xte)
    metrics = {"accuracy": float(accuracy_score(yte, pred)),
               "macro_f1": float(f1_score(yte, pred, average="macro", zero_division=0)),
               "n_train": len(X_train), "n_test": len(Xte), "n_user": len(ux), "eval_on": eval_on}
    rep = pd.DataFrame(classification_report(yte, pred, output_dict=True, zero_division=0)).T
    rep = rep.drop(index=["accuracy", "macro avg", "weighted avg"], errors="ignore")
    final = _make_pipeline(C).fit(bx + ux, by + uy)  # refit on everything for actual use
    return final, metrics, rep


def save_categorizer(model, user_id):
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, model_path(user_id))


def load_categorizer(user_id):
    p = model_path(user_id)
    if os.path.exists(p):
        try:
            return joblib.load(p)
        except Exception:
            pass
    return train_categorizer()

# --------------------------------------------------------- savings advisor
# Max share of each category's forecast that can realistically be cut
FLEX = {"Entertainment": 0.50, "Shopping": 0.40, "Food & Dining": 0.30, "Other": 0.30,
        "Transport": 0.15, "Groceries": 0.10, "Education": 0.05, "Bills & Utilities": 0.05, "Health": 0.0}


def forecast_next_income(df):
    inc = df[df["type"] == "Income"]
    if inc.empty:
        return 0.0
    monthly = inc.groupby(inc["date"].dt.to_period("M"))["amount"].sum()
    past = monthly[monthly.index < pd.Timestamp.today().to_period("M")].tail(3)
    return float((past if len(past) else monthly).mean())


def savings_plan(df, target_savings):
    """Spread the needed cut across categories, weighted by how flexible each one is."""
    exp = df[df["type"] == "Expense"]
    fc = forecast_next_month(exp)
    income = forecast_next_income(df)
    total_fc = float(fc.sum())
    predicted = income - total_fc
    gap = max(target_savings - predicted, 0.0)
    summary = {"income": income, "forecast_expenses": total_fc, "predicted_savings": predicted,
               "target": float(target_savings), "gap": gap, "achievable": 0.0, "reachable": True}
    if fc.empty:
        return pd.DataFrame(), summary

    cap = pd.Series({c: fc[c] * FLEX.get(c, 0.2) for c in fc.index})
    capacity = float(cap.sum())
    achievable = min(gap, capacity)
    cut = cap * (achievable / capacity) if capacity > 0 else cap * 0
    summary.update(achievable=achievable, reachable=gap <= capacity + 1e-9)

    pv = monthly_by_category(exp)
    hist = pv[pv.index < pd.Timestamp.today().to_period("M").to_timestamp()].tail(6).mean()
    plan = pd.DataFrame({"category": fc.index, "forecast": fc.values, "cut": cut.reindex(fc.index).values})
    plan["new_budget"] = plan["forecast"] - plan["cut"]
    plan["cut_pct"] = plan["cut"] / plan["forecast"]

    def why(r):
        h = hist.get(r["category"], 0)
        if h > 0 and r["forecast"] > h * 1.1:
            return f"Forecast is {r['forecast'] / h - 1:.0%} above your usual"
        if FLEX.get(r["category"], 0.2) >= 0.3:
            return "Flexible, non-essential spending"
        return "Small trim on a necessary category"
    plan["why"] = plan.apply(why, axis=1)
    return plan[plan["cut"] > 0.005].sort_values("cut", ascending=False).reset_index(drop=True), summary