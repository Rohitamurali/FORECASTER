import { useState } from "react";
import { Link } from "react-router-dom";
import API from "../services/api";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const login = async (e) => {
    e?.preventDefault();
    try {
      setLoading(true);
      setError("");
      const res = await API.post("/auth/login", { email, password });
      localStorage.setItem("token", res.data.access_token);
      localStorage.setItem("user", JSON.stringify(res.data.user));
      window.location.href = "/dashboard";
    } catch (err) {
      let errMsg = err.response?.data?.detail || err.response?.data?.message || "Invalid email or password";
      if (Array.isArray(errMsg)) {
        errMsg = errMsg.map(e => e.msg).join(", ");
      } else if (typeof errMsg === "object") {
        errMsg = JSON.stringify(errMsg);
      }
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-layout">
        <section className="auth-hero">
          <div className="auth-brand-mark">CapForecast</div>
          <h1>Predict capacity before it becomes a problem</h1>
          <p>
            Monitor infrastructure usage, forecast resource limits, and get
            actionable insights — all from one workspace.
          </p>
          <div className="auth-features">
            <div className="auth-feature">
              <strong>Smart forecasting</strong>
              <span>ARIMA & linear regression engines</span>
            </div>
            <div className="auth-feature">
              <strong>Natural language</strong>
              <span>Ask questions in plain English</span>
            </div>
            <div className="auth-feature">
              <strong>Live monitoring</strong>
              <span>Health scores and real-time alerts</span>
            </div>
          </div>
        </section>

        <form className="auth-card" onSubmit={login}>
          <h2>Sign in</h2>
          <p>Enter your credentials to access your workspace.</p>

          <label>
            Work email
            <input
              className="input"
              type="email"
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>

          <label>
            Password
            <input
              className="input"
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>

          <button className="button" type="submit" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
          </button>

          {error && <div className="error">{error}</div>}

          <Link className="link" to="/register">
            Create an account
          </Link>
        </form>
      </div>
    </div>
  );
}
