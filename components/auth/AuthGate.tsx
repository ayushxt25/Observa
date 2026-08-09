"use client";

import { useState, type ReactNode } from "react";
import { useAuth } from "@/components/providers/AuthProvider";

export function AuthGate({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");

  if (auth.status === "loading") return <main className="dashboard-page"><section className="panel"><h2>Loading session...</h2></section></main>;
  if (auth.status === "authenticated") return <>{children}</>;

  return (
    <main className="dashboard-page auth-page">
      <section className="panel auth-panel">
        <div className="section-heading">
          <h2>{mode === "login" ? "Sign in" : "Create account"}</h2>
          <span>{auth.error ?? "Observa workspace access"}</span>
        </div>
        <label>Email<input value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" /></label>
        {mode === "register" ? <label>Name<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} autoComplete="name" /></label> : null}
        <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
        <div className="auth-actions">
          <button type="button" onClick={() => void (mode === "login" ? auth.login(email, password) : auth.register(email, password, displayName || undefined))}>{mode === "login" ? "Sign in" : "Register"}</button>
          <button type="button" className="ghost" onClick={() => setMode(mode === "login" ? "register" : "login")}>{mode === "login" ? "Need an account?" : "Have an account?"}</button>
        </div>
      </section>
    </main>
  );
}
