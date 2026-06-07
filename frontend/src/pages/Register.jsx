import { useState } from "react";
import { Link } from "react-router-dom";
import API from "../services/api";

export default function Register() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const register = async (e) => {
    e.preventDefault();
    try {
      setLoading(true);
      setError("");
      await API.post("/auth/register", { name, email, password });
      window.location.href = "/";
    } catch (err) {
      let errMsg = err.response?.data?.detail || err.response?.data?.message || "Registration failed";
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
      <form className="auth-card solo" onSubmit={register}>
        <div className="auth-brand-mark solo-mark">CapForecast</div>
        <h2>Create your account</h2>
        <p>Get started with capacity planning and forecasting.</p>

        <label>
          Full name
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </label>

        <label>
          Email
          <input
            className="input"
            type="email"
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
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
          />
        </label>

        <button className="button green" type="submit" disabled={loading}>
          {loading ? "Creating..." : "Register"}
        </button>

        {error && <div className="error">{error}</div>}

        <Link className="link" to="/">
          Back to login
        </Link>
      </form>
    </div>
  );
}
