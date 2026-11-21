import warnings
warnings.filterwarnings("ignore")

import sys
from pathlib import Path

# Ensure project root is in sys.path for direct execution (python app/main.py)
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.db import db
from app.engine import engine
from app.schemas import (
    AdminDashboardResponse,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminUserDetailResponse,
    ApiKeyResponse,
    AuthResponse,
    DeleteResponse,
    ExportResponse,
    HealthResponse,
    ImportRequest,
    ImportResponse,
    KeyCreateRequest,
    KeyCreateResponse,
    LearnRequest,
    LearnResponse,
    ProfileResponse,
    RecallRequest,
    RecallResponse,
    ResetResponse,
    StatsResponse,
    UserCreateRequest,
    UserCreateResponse,
    UserLoginRequest,
    UserSignUpRequest,
    UserStatusUpdateRequest,
)
from app.security import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    create_user_session,
    get_or_generate_api_key,
    invalidate_session,
    verify_admin,
    verify_admin_credentials,
    verify_user_key,
)

logger = logging.getLogger("nova.brain.api")

app = FastAPI(
    title="NOVA Cloud Brain (MaaS)",
    description="Multi-Tenant Memory-as-a-Service with Admin Telemetry & Observability.",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Cross-Origin Resource Sharing (for Flutter Mobile App, PC Assistant, Web clients)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Interactive Web Console & Portal UI
# ============================================================

@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
def web_console():
    """Interactive Web Console for managing NOVA Memory-as-a-Service."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NOVA MaaS - Cloud Brain &amp; Multi-Tenant Console</title>
    <style>
        :root {
            --bg: #090d16;
            --card-bg: #111827;
            --card-border: #1f2937;
            --card-hover: #1e293b;
            --accent: #3b82f6;
            --accent-hover: #2563eb;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --text-main: #f9fafb;
            --text-muted: #9ca3af;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 24px 16px;
        }
        .container { max-width: 1060px; width: 100%; }
        
        /* Navbar */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--card-border);
        }
        .logo-area { display: flex; align-items: center; gap: 12px; }
        .logo-badge {
            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
            width: 44px;
            height: 44px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            font-weight: 800;
            box-shadow: 0 4px 14px rgba(59, 130, 246, 0.4);
        }
        .header h1 { font-size: 20px; font-weight: 700; letter-spacing: -0.5px; }
        .header p { font-size: 13px; color: var(--text-muted); }
        .header-actions { display: flex; align-items: center; gap: 12px; }
        
        .status-pill {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(16, 185, 129, 0.1);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.2);
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
        }
        .pulse { width: 8px; height: 8px; background: var(--success); border-radius: 50%; box-shadow: 0 0 8px var(--success); }

        .btn {
            background: var(--accent);
            color: #fff;
            border: none;
            padding: 9px 18px;
            font-size: 13px;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }
        .btn:hover { background: var(--accent-hover); }
        .btn-danger { background: var(--danger); }
        .btn-danger:hover { background: #dc2626; }
        .btn-warning { background: var(--warning); color: #000; }
        .btn-secondary { background: #1f2937; color: #e5e7eb; border: 1px solid var(--card-border); }
        .btn-secondary:hover { background: #374151; }
        .btn-sm { padding: 5px 10px; font-size: 12px; border-radius: 6px; }

        .input-group { margin-bottom: 14px; text-align: left; }
        .input-group label { display: block; font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px; }
        .input-control {
            width: 100%;
            background: #0b1120;
            border: 1px solid var(--card-border);
            color: #fff;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            outline: none;
            transition: border-color 0.2s;
        }
        .input-control:focus { border-color: var(--accent); }
        textarea.input-control { min-height: 80px; resize: vertical; }

        /* Auth Gate Box */
        .auth-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 32px 28px;
            max-width: 440px;
            margin: 40px auto;
            text-align: center;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
        }
        .auth-tabs { display: flex; border-bottom: 1px solid var(--card-border); margin-bottom: 24px; }
        .auth-tab-btn {
            flex: 1;
            padding: 12px;
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
        }
        .auth-tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
        .auth-hint {
            margin-top: 20px;
            padding: 12px;
            background: rgba(59, 130, 246, 0.08);
            border: 1px solid rgba(59, 130, 246, 0.2);
            border-radius: 8px;
            font-size: 12px;
            color: #93c5fd;
            text-align: left;
            line-height: 1.5;
        }

        /* Dashboard Views */
        .dashboard-view { display: none; }
        .active-view { display: block !important; }

        .key-banner {
            background: rgba(59, 130, 246, 0.08);
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            flex-wrap: wrap;
        }
        .key-val {
            font-family: 'Consolas', monospace;
            font-size: 14px;
            font-weight: 700;
            color: #38bdf8;
            margin-top: 4px;
            word-break: break-all;
            background: #0b1120;
            padding: 6px 10px;
            border-radius: 6px;
            border: 1px solid var(--card-border);
            display: inline-block;
        }

        .tabs { display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 1px solid var(--card-border); padding-bottom: 8px; overflow-x: auto; }
        .tab-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 8px 16px;
            font-size: 13px;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
            white-space: nowrap;
        }
        .tab-btn.active { background: #1f2937; color: #fff; }
        .tab-btn:hover:not(.active) { color: #fff; background: rgba(255,255,255,0.03); }

        .panel { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 14px; padding: 22px; display: none; }
        .panel.active { display: block; }

        .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 22px; }
        .stat-box { background: #0b1120; border: 1px solid var(--card-border); border-radius: 10px; padding: 16px; }
        .stat-box .title { font-size: 11px; color: var(--text-muted); text-transform: uppercase; font-weight: 600; }
        .stat-box .num { font-size: 24px; font-weight: 800; margin-top: 6px; color: #fff; }

        .table-responsive { overflow-x: auto; margin-top: 14px; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th, td { padding: 12px 14px; text-align: left; border-bottom: 1px solid var(--card-border); }
        th { color: var(--text-muted); font-size: 11px; text-transform: uppercase; background: #0b1120; }
        tr:hover { background: rgba(255,255,255,0.02); }
        
        .badge { padding: 4px 10px; border-radius: 9999px; font-size: 11px; font-weight: 700; }
        .badge-active { background: rgba(16, 185, 129, 0.15); color: #34d399; }
        .badge-suspended { background: rgba(239, 68, 68, 0.15); color: #f87171; }
        .badge-admin { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }
        .badge-user { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }

        .memory-list { margin-top: 16px; display: flex; flex-direction: column; gap: 10px; max-height: 420px; overflow-y: auto; }
        .memory-item {
            background: #0b1120;
            border: 1px solid var(--card-border);
            padding: 14px;
            border-radius: 10px;
            font-size: 13px;
            line-height: 1.5;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
        }

        .alert-error {
            background: rgba(239, 68, 68, 0.12);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #fca5a5;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 14px;
            text-align: left;
        }
        .alert-success {
            background: rgba(16, 185, 129, 0.12);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: #6ee7b7;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 14px;
            text-align: left;
        }
        .code-box {
            background: #0b1120;
            border: 1px solid var(--card-border);
            padding: 12px;
            border-radius: 8px;
            font-family: monospace;
            font-size: 12px;
            color: #a5f3fc;
            overflow-x: auto;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <div class="logo-area">
                <div class="logo-badge">N</div>
                <div>
                    <h1>NOVA Cloud Brain (MaaS)</h1>
                    <p>Enterprise Memory-as-a-Service &amp; Observability Portal</p>
                </div>
            </div>
            <div class="header-actions">
                <div id="user-pill" style="display: none; align-items: center; gap: 10px;">
                    <span id="user-display-name" style="font-size: 13px; font-weight: 600;">User</span>
                    <span id="user-role-badge" class="badge badge-user">user</span>
                    <button class="btn btn-secondary btn-sm" onclick="logoutSession()">Sign Out</button>
                </div>
                <div id="public-status-pill" class="status-pill">
                    <span class="pulse"></span>
                    <span>Brain Online</span>
                </div>
            </div>
        </div>

        <!-- ========================================================= -->
        <!-- VIEW 1: AUTHENTICATION GATEWAY (LOGIN / SIGN UP)           -->
        <!-- ========================================================= -->
        <div id="view-auth" class="dashboard-view active-view">
            <div class="auth-card">
                <div class="auth-tabs">
                    <button class="auth-tab-btn active" id="btn-tab-signin" onclick="switchAuthTab('signin')">Sign In</button>
                    <button class="auth-tab-btn" id="btn-tab-signup" onclick="switchAuthTab('signup')">Create Account</button>
                </div>

                <!-- Sign In Form -->
                <div id="form-signin">
                    <div id="signin-alert" style="display: none;"></div>
                    <div class="input-group">
                        <label>Email, Username, or Full Name</label>
                        <input id="login-id" class="input-control" type="text" placeholder="e.g. admin, test1@gmail.com, or test 1" />
                    </div>
                    <div class="input-group">
                        <label>Password</label>
                        <input id="login-pass" class="input-control" type="password" placeholder="Enter your password" />
                    </div>
                    <button class="btn" style="width: 100%; margin-top: 8px;" onclick="doLogin()">Sign In</button>
                    
                    <div class="auth-hint">
                        <strong>Default Admin Credentials:</strong><br>
                        Username: <code>admin</code> &nbsp;|&nbsp; Password: <code>admin123</code><br>
                        <span style="font-size: 11px; color: #94a3b8;">Or click 'Create Account' above to sign up as a new user.</span>
                    </div>
                </div>

                <!-- Sign Up Form -->
                <div id="form-signup" style="display: none;">
                    <div id="signup-alert" style="display: none;"></div>
                    <div class="input-group">
                        <label>Full Name</label>
                        <input id="signup-name" class="input-control" type="text" placeholder="e.g. John Doe" />
                    </div>
                    <div class="input-group">
                        <label>Email Address</label>
                        <input id="signup-email" class="input-control" type="email" placeholder="e.g. john@example.com" />
                    </div>
                    <div class="input-group">
                        <label>Choose Password</label>
                        <input id="signup-pass" class="input-control" type="password" placeholder="At least 4 characters" />
                    </div>
                    <button class="btn" style="width: 100%; margin-top: 8px;" onclick="doSignUp()">Create Account &amp; Generate Key</button>
                    <div class="auth-hint">
                        Each new account automatically receives a unique API key and an isolated private memory partition.
                    </div>
                </div>
            </div>
        </div>

        <!-- ========================================================= -->
        <!-- VIEW 2: USER CONSOLE (FOR REGULAR USERS)                  -->
        <!-- ========================================================= -->
        <div id="view-user" class="dashboard-view">
            <!-- User API Key Showcase -->
            <div class="key-banner">
                <div>
                    <div style="font-size: 12px; font-weight: 600; text-transform: uppercase; color: var(--text-muted);">Your Private API Key</div>
                    <div class="key-val" id="user-api-key-val">nb_live_...</div>
                </div>
                <div style="display: flex; gap: 8px;">
                    <button class="btn btn-secondary btn-sm" onclick="copyUserKey()">Copy Key</button>
                    <button class="btn btn-secondary btn-sm" onclick="generateNewUserKey()">Generate New</button>
                </div>
            </div>

            <!-- User Tabs -->
            <div class="tabs">
                <button class="tab-btn active" onclick="switchUserTab('recall')">Recall Search</button>
                <button class="tab-btn" onclick="switchUserTab('learn')">Teach Brain</button>
                <button class="tab-btn" onclick="switchUserTab('profile')">Knowledge Profile</button>
                <button class="tab-btn" onclick="switchUserTab('manage')">Manage &amp; Reset</button>
            </div>

            <!-- Tab: Recall -->
            <div id="user-tab-recall" class="panel active">
                <h3 style="margin-bottom: 12px; font-size: 16px;">Semantic Memory Recall</h3>
                <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 16px;">
                    Hybrid semantic search across all long-term memories stored in your private cloud brain partition.
                </p>
                <div class="input-group">
                    <label>Search Query</label>
                    <input id="user-recall-query" class="input-control" type="text" placeholder="e.g. What is my favorite programming language?" />
                </div>
                <button class="btn" onclick="doUserRecall()">Search Brain</button>
                <div id="user-recall-results" class="memory-list"></div>
            </div>

            <!-- Tab: Teach -->
            <div id="user-tab-learn" class="panel">
                <h3 style="margin-bottom: 12px; font-size: 16px;">Teach Brain (Add Memory)</h3>
                <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 16px;">
                    Teach your AI assistant new facts, preferences, or conversation logs.
                </p>
                <div id="user-learn-alert" style="display: none;"></div>
                <div class="input-group">
                    <label>Interaction Message / Statement</label>
                    <textarea id="user-learn-text" class="input-control" placeholder="e.g. I prefer dark mode and love Python FastAPI."></textarea>
                </div>
                <button class="btn" onclick="doUserLearn()">Persist to Brain</button>
            </div>

            <!-- Tab: Profile -->
            <div id="user-tab-profile" class="panel">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                    <div>
                        <h3 style="font-size: 16px;">Knowledge Profile</h3>
                        <p style="font-size: 13px; color: var(--text-muted);">Consolidated summary of everything your cloud brain remembers about you.</p>
                    </div>
                    <button class="btn btn-secondary btn-sm" onclick="loadUserProfile()">Refresh Profile</button>
                </div>
                <div id="user-profile-summary-box" style="background: #0b1120; border: 1px solid var(--card-border); padding: 16px; border-radius: 10px; margin-bottom: 16px; font-size: 13px; line-height: 1.6;">
                    Click 'Refresh Profile' to synthesize your knowledge profile.
                </div>
                <h4 style="font-size: 13px; color: var(--text-muted); text-transform: uppercase;">All Extracted Facts (<span id="user-facts-count">0</span>)</h4>
                <div id="user-facts-list" class="memory-list"></div>
            </div>

            <!-- Tab: Manage & Reset -->
            <div id="user-tab-manage" class="panel">
                <h3 style="margin-bottom: 12px; font-size: 16px;">Memory Portability &amp; Privacy</h3>
                <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 20px;">
                    Export your memories to JSON backup, or permanently wipe your partition with 1 click.
                </p>
                
                <div style="display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap;">
                    <button class="btn btn-secondary" onclick="doUserExport()">Export Memories (JSON)</button>
                    <button class="btn btn-danger" onclick="doUserReset()">Wipe Out All My Memories</button>
                </div>

                <div class="code-box" id="user-export-code" style="display: none; max-height: 250px;"></div>

                <div style="margin-top: 24px; padding-top: 18px; border-top: 1px solid var(--card-border);">
                    <h4 style="font-size: 14px; margin-bottom: 8px;">Python Assistant Client Integration</h4>
                    <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 10px;">Paste this in your local <code>assistant/memory/maas_client.py</code>:</p>
                    <div class="code-box" id="user-snippet">
from assistant.memory.maas_client import NovaBrainClient

client = NovaBrainClient(
    base_url="http://localhost:8000",
    api_key="YOUR_API_KEY"
)
client.learn("My favorite database is PostgreSQL")
memories = client.recall("database")
                    </div>
                </div>
            </div>
        </div>

        <!-- ========================================================= -->
        <!-- VIEW 3: ADMIN OBSERVABILITY SUITE                         -->
        <!-- ========================================================= -->
        <div id="view-admin" class="dashboard-view">
            <!-- Admin Global Metrics -->
            <div class="stat-grid">
                <div class="stat-box">
                    <div class="title">Total Users</div>
                    <div class="num" id="stat-users">0</div>
                </div>
                <div class="stat-box">
                    <div class="title">Active API Keys</div>
                    <div class="num" id="stat-keys">0</div>
                </div>
                <div class="stat-box">
                    <div class="title">Total API Requests</div>
                    <div class="num" id="stat-reqs">0</div>
                </div>
                <div class="stat-box">
                    <div class="title">Avg Latency</div>
                    <div class="num" id="stat-latency">0ms</div>
                </div>
            </div>

            <!-- Admin Tabs -->
            <div class="tabs">
                <button class="tab-btn active" onclick="switchAdminTab('users')">User Directory &amp; Usage</button>
                <button class="tab-btn" onclick="switchAdminTab('logs')">Live Request Audit Logs</button>
            </div>

            <!-- Tab: Users Directory -->
            <div id="admin-tab-users" class="panel active">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                    <div>
                        <h3 style="font-size: 16px;">Registered Users &amp; Telemetry</h3>
                        <p style="font-size: 13px; color: var(--text-muted);">Inspect activity, monitor usage, manage keys, or suspend users.</p>
                    </div>
                    <button class="btn btn-secondary btn-sm" onclick="loadAdminDashboard()">Refresh</button>
                </div>

                <div class="table-responsive">
                    <table>
                        <thead>
                            <tr>
                                <th>User ID</th>
                                <th>Name</th>
                                <th>Email</th>
                                <th>Total Requests</th>
                                <th>Last Active</th>
                                <th>Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="admin-users-table-body">
                            <tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Loading users...</td></tr>
                        </tbody>
                    </table>
                </div>

                <!-- Deep Dive User Inspector Modal/Box -->
                <div id="admin-user-inspector" style="display: none; margin-top: 24px; padding: 20px; background: #0b1120; border: 1px solid var(--accent); border-radius: 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                        <h4 id="inspector-user-title" style="font-size: 15px; color: #60a5fa;">User Details</h4>
                        <button class="btn btn-secondary btn-sm" onclick="closeUserInspector()">Close</button>
                    </div>
                    <div id="inspector-user-content"></div>
                </div>
            </div>

            <!-- Tab: Audit Logs -->
            <div id="admin-tab-logs" class="panel">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                    <div>
                        <h3 style="font-size: 16px;">Live Request Audit Trace</h3>
                        <p style="font-size: 13px; color: var(--text-muted);">Immutable audit log of all client interactions.</p>
                    </div>
                    <button class="btn btn-secondary btn-sm" onclick="loadAdminDashboard()">Refresh Logs</button>
                </div>
                <div class="table-responsive">
                    <table>
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>User ID</th>
                                <th>Endpoint</th>
                                <th>Method</th>
                                <th>Latency</th>
                                <th>Status</th>
                                <th>Details</th>
                            </tr>
                        </thead>
                        <tbody id="admin-logs-table-body">
                            <tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Loading audit logs...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- Frontend Application Logic -->
    <script>
        // Session State
        let currentSession = null;

        // Restore Session on Load
        window.addEventListener('DOMContentLoaded', () => {
            const saved = localStorage.getItem('nova_auth_session');
            if (saved) {
                try {
                    currentSession = JSON.parse(saved);
                    applySessionState();
                } catch (e) {
                    localStorage.removeItem('nova_auth_session');
                    showAuthGateway();
                }
            } else {
                showAuthGateway();
            }
        });

        function switchAuthTab(tab) {
            document.getElementById('btn-tab-signin').className = 'auth-tab-btn ' + (tab === 'signin' ? 'active' : '');
            document.getElementById('btn-tab-signup').className = 'auth-tab-btn ' + (tab === 'signup' ? 'active' : '');
            document.getElementById('form-signin').style.display = tab === 'signin' ? 'block' : 'none';
            document.getElementById('form-signup').style.display = tab === 'signup' ? 'block' : 'none';
        }

        function showAuthGateway() {
            document.getElementById('view-auth').className = 'dashboard-view active-view';
            document.getElementById('view-user').className = 'dashboard-view';
            document.getElementById('view-admin').className = 'dashboard-view';
            document.getElementById('user-pill').style.display = 'none';
            document.getElementById('public-status-pill').style.display = 'flex';
        }

        function applySessionState() {
            if (!currentSession) {
                showAuthGateway();
                return;
            }

            document.getElementById('view-auth').className = 'dashboard-view';
            document.getElementById('user-pill').style.display = 'flex';
            document.getElementById('public-status-pill').style.display = 'none';
            document.getElementById('user-display-name').innerText = currentSession.user.name || currentSession.user.email;
            
            const roleBadge = document.getElementById('user-role-badge');
            roleBadge.innerText = currentSession.user.role;
            roleBadge.className = 'badge ' + (currentSession.user.role === 'admin' ? 'badge-admin' : 'badge-user');

            if (currentSession.user.role === 'admin') {
                document.getElementById('view-admin').className = 'dashboard-view active-view';
                document.getElementById('view-user').className = 'dashboard-view';
                loadAdminDashboard();
            } else {
                document.getElementById('view-user').className = 'dashboard-view active-view';
                document.getElementById('view-admin').className = 'dashboard-view';
                document.getElementById('user-api-key-val').innerText = currentSession.api_key;
                document.getElementById('user-snippet').innerText = 
`from assistant.memory.maas_client import NovaBrainClient

client = NovaBrainClient(
    base_url="http://localhost:8000",
    api_key="${currentSession.api_key}"
)
client.learn("I am exploring NOVA Cloud Brain MaaS.")
memories = client.recall("explore")
print(memories)`;
                loadUserProfile();
            }
        }

        async function doLogin() {
            const email = document.getElementById('login-id').value.trim();
            const pass = document.getElementById('login-pass').value.trim();
            const alertBox = document.getElementById('signin-alert');
            alertBox.style.display = 'none';

            if (!email || !pass) {
                alertBox.className = 'alert-error';
                alertBox.innerText = 'Please enter your username/email and password.';
                alertBox.style.display = 'block';
                return;
            }

            try {
                const res = await fetch('/v1/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: email, password: pass })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Login failed.');

                currentSession = data;
                localStorage.setItem('nova_auth_session', JSON.stringify(data));
                applySessionState();
            } catch (err) {
                alertBox.className = 'alert-error';
                alertBox.innerText = err.message;
                alertBox.style.display = 'block';
            }
        }

        async function doSignUp() {
            const name = document.getElementById('signup-name').value.trim();
            const email = document.getElementById('signup-email').value.trim();
            const pass = document.getElementById('signup-pass').value.trim();
            const alertBox = document.getElementById('signup-alert');
            alertBox.style.display = 'none';

            if (!name || !email || !pass) {
                alertBox.className = 'alert-error';
                alertBox.innerText = 'Name, email, and password are required.';
                alertBox.style.display = 'block';
                return;
            }

            try {
                const res = await fetch('/v1/auth/signup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name, email: email, password: pass })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Registration failed.');

                currentSession = data;
                localStorage.setItem('nova_auth_session', JSON.stringify(data));
                applySessionState();
            } catch (err) {
                alertBox.className = 'alert-error';
                alertBox.innerText = err.message;
                alertBox.style.display = 'block';
            }
        }

        function logoutSession() {
            if (currentSession && currentSession.token) {
                fetch('/v1/auth/logout', {
                    method: 'POST',
                    headers: { 'X-Session-Token': currentSession.token }
                }).catch(() => {});
            }
            currentSession = null;
            localStorage.removeItem('nova_auth_session');
            showAuthGateway();
        }

        // =========================================================
        // USER PORTAL ACTIONS
        // =========================================================

        function switchUserTab(tab) {
            ['recall', 'learn', 'profile', 'manage'].forEach(t => {
                document.getElementById('user-tab-' + t).className = 'panel ' + (t === tab ? 'active' : '');
            });
            const btns = document.querySelectorAll('#view-user .tabs .tab-btn');
            btns.forEach((b, i) => {
                b.className = 'tab-btn ' + (['recall', 'learn', 'profile', 'manage'][i] === tab ? 'active' : '');
            });
        }

        function copyUserKey() {
            if (!currentSession || !currentSession.api_key) return;
            navigator.clipboard.writeText(currentSession.api_key);
            alert('API Key copied to clipboard!');
        }

        async function generateNewUserKey() {
            if (!confirm('Are you sure you want to generate a new API key?')) return;
            try {
                const res = await fetch('/v1/auth/keys/generate', {
                    method: 'POST',
                    headers: { 'X-Session-Token': currentSession.token }
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Failed to generate key.');
                currentSession.api_key = data.api_key;
                localStorage.setItem('nova_auth_session', JSON.stringify(currentSession));
                document.getElementById('user-api-key-val').innerText = data.api_key;
                alert('New API Key generated successfully!');
            } catch (err) {
                alert('Error: ' + err.message);
            }
        }

        async function doUserRecall() {
            const query = document.getElementById('user-recall-query').value.trim();
            const resultsBox = document.getElementById('user-recall-results');
            if (!query) { alert('Please enter a query.'); return; }
            resultsBox.innerHTML = '<span style="color: var(--text-muted);">Searching memory partition...</span>';

            try {
                const res = await fetch('/v1/recall', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-API-Key': currentSession.api_key
                    },
                    body: JSON.stringify({ query: query, top_k: 5 })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Recall failed.');

                if (!data.memories || data.memories.length === 0) {
                    resultsBox.innerHTML = '<div style="color: var(--text-muted);">No matching memories found for this query.</div>';
                    return;
                }

                resultsBox.innerHTML = data.memories.map((m, i) => `
                    <div class="memory-item">
                        <div>
                            <span style="color: #60a5fa; font-weight: 600;">#${i + 1}</span> &nbsp;
                            <span>${m}</span>
                        </div>
                    </div>
                `).join('');
            } catch (err) {
                resultsBox.innerHTML = `<div style="color: var(--danger);">Error: ${err.message}</div>`;
            }
        }

        async function doUserLearn() {
            const text = document.getElementById('user-learn-text').value.trim();
            const alertBox = document.getElementById('user-learn-alert');
            if (!text) { alert('Please enter a statement or conversation.'); return; }

            try {
                const res = await fetch('/v1/learn', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-API-Key': currentSession.api_key
                    },
                    body: JSON.stringify({ message: text, agent_id: 'web_portal' })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Learn failed.');

                alertBox.className = 'alert-success';
                alertBox.innerText = 'Fact queued successfully for background extraction!';
                alertBox.style.display = 'block';
                document.getElementById('user-learn-text').value = '';
                setTimeout(() => { loadUserProfile(); }, 2000);
            } catch (err) {
                alertBox.className = 'alert-error';
                alertBox.innerText = err.message;
                alertBox.style.display = 'block';
            }
        }

        async function loadUserProfile() {
            const summaryBox = document.getElementById('user-profile-summary-box');
            const factsList = document.getElementById('user-facts-list');
            const countSpan = document.getElementById('user-facts-count');

            try {
                const res = await fetch('/v1/profile', {
                    headers: { 'X-API-Key': currentSession.api_key }
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Profile synthesis failed.');

                summaryBox.innerText = data.summary || 'No knowledge facts recorded yet.';
                countSpan.innerText = data.total_facts || 0;

                if (!data.facts || data.facts.length === 0) {
                    factsList.innerHTML = '<div style="color: var(--text-muted);">No individual facts in your brain yet. Use "Teach Brain" to add some!</div>';
                    return;
                }

                // Also fetch all memories to get IDs for delete buttons
                const memRes = await fetch('/v1/memories', {
                    headers: { 'X-API-Key': currentSession.api_key }
                });
                const memList = await memRes.json();

                factsList.innerHTML = memList.map(m => `
                    <div class="memory-item">
                        <span>${m.memory || m.text || JSON.stringify(m)}</span>
                        <button class="btn btn-danger btn-sm" onclick="deleteUserMemory('${m.id}')">Delete</button>
                    </div>
                `).join('');
            } catch (err) {
                summaryBox.innerText = 'Error loading profile: ' + err.message;
            }
        }

        async function deleteUserMemory(memId) {
            if (!confirm('Delete this memory?')) return;
            try {
                const res = await fetch('/v1/memories/' + memId, {
                    method: 'DELETE',
                    headers: { 'X-API-Key': currentSession.api_key }
                });
                if (!res.ok) throw new Error('Failed to delete memory.');
                loadUserProfile();
            } catch (err) {
                alert('Error: ' + err.message);
            }
        }

        async function doUserExport() {
            try {
                const res = await fetch('/v1/export', {
                    headers: { 'X-API-Key': currentSession.api_key }
                });
                const data = await res.json();
                const codeBox = document.getElementById('user-export-code');
                codeBox.innerText = JSON.stringify(data, null, 2);
                codeBox.style.display = 'block';
            } catch (err) {
                alert('Export failed: ' + err.message);
            }
        }

        async function doUserReset() {
            if (!confirm('DANGER: This will permanently wipe all your memories from the cloud brain. Are you sure?')) return;
            try {
                const res = await fetch('/v1/users/reset', {
                    method: 'DELETE',
                    headers: { 'X-API-Key': currentSession.api_key }
                });
                const data = await res.json();
                alert(data.message || 'Brain partition wiped.');
                loadUserProfile();
            } catch (err) {
                alert('Reset failed: ' + err.message);
            }
        }

        // =========================================================
        // ADMIN DASHBOARD ACTIONS
        // =========================================================

        function switchAdminTab(tab) {
            document.getElementById('admin-tab-users').className = 'panel ' + (tab === 'users' ? 'active' : '');
            document.getElementById('admin-tab-logs').className = 'panel ' + (tab === 'logs' ? 'active' : '');
            const btns = document.querySelectorAll('#view-admin .tabs .tab-btn');
            btns[0].className = 'tab-btn ' + (tab === 'users' ? 'active' : '');
            btns[1].className = 'tab-btn ' + (tab === 'logs' ? 'active' : '');
        }

        async function loadAdminDashboard() {
            if (!currentSession || currentSession.user.role !== 'admin') return;

            try {
                const res = await fetch('/v1/admin/dashboard', {
                    headers: { 'X-Admin-Token': currentSession.token }
                });
                if (res.status === 401) { logoutSession(); return; }
                const data = await res.json();

                // Metrics
                document.getElementById('stat-users').innerText = data.metrics.total_users;
                document.getElementById('stat-keys').innerText = data.metrics.active_keys;
                document.getElementById('stat-reqs').innerText = data.metrics.total_requests;
                document.getElementById('stat-latency').innerText = data.metrics.avg_latency_ms + 'ms';

                // Users Table
                const tbody = document.getElementById('admin-users-table-body');
                if (!data.users || data.users.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No regular users provisioned yet. New signups will appear here.</td></tr>';
                } else {
                    tbody.innerHTML = data.users.map(u => `
                        <tr>
                            <td style="font-family: monospace; font-size: 11px; color: #93c5fd;">${u.id}</td>
                            <td><strong>${u.name}</strong></td>
                            <td>${u.email}</td>
                            <td>${u.total_requests} reqs</td>
                            <td style="font-size: 11px; color: var(--text-muted);">${u.last_active}</td>
                            <td><span class="badge ${u.status === 'active' ? 'badge-active' : 'badge-suspended'}">${u.status}</span></td>
                            <td>
                                <div style="display: flex; gap: 6px;">
                                    <button class="btn btn-secondary btn-sm" onclick="inspectAdminUser('${u.id}')">Inspect</button>
                                    <button class="btn btn-sm ${u.status === 'active' ? 'btn-warning' : 'btn-secondary'}" onclick="toggleUserStatus('${u.id}', '${u.status === 'active' ? 'suspended' : 'active'}')">
                                        ${u.status === 'active' ? 'Suspend' : 'Activate'}
                                    </button>
                                    <button class="btn btn-danger btn-sm" onclick="deleteAdminUser('${u.id}')">Delete</button>
                                </div>
                            </td>
                        </tr>
                    `).join('');
                }

                // Logs Table
                const logsBody = document.getElementById('admin-logs-table-body');
                if (!data.recent_logs || data.recent_logs.length === 0) {
                    logsBody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No requests recorded yet.</td></tr>';
                } else {
                    logsBody.innerHTML = data.recent_logs.map(l => `
                        <tr>
                            <td style="font-size: 11px; color: var(--text-muted);">${l.timestamp ? l.timestamp.slice(11, 19) : ''}</td>
                            <td style="font-family: monospace; font-size: 11px;">${l.user_id}</td>
                            <td style="color: #38bdf8;">${l.endpoint}</td>
                            <td><span class="badge" style="background:#1e293b;">${l.method}</span></td>
                            <td>${l.latency_ms}ms</td>
                            <td><span class="badge ${l.status_code === 200 || l.status_code === 202 ? 'badge-active' : 'badge-suspended'}">${l.status_code}</span></td>
                            <td style="font-size: 12px; color: #94a3b8; max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${l.details || ''}</td>
                        </tr>
                    `).join('');
                }
            } catch (err) {
                alert('Admin dashboard error: ' + err.message);
            }
        }

        async function inspectAdminUser(userId) {
            const inspector = document.getElementById('admin-user-inspector');
            const title = document.getElementById('inspector-user-title');
            const content = document.getElementById('inspector-user-content');
            inspector.style.display = 'block';
            content.innerHTML = '<span style="color: var(--text-muted);">Loading user partition details...</span>';

            try {
                const res = await fetch('/v1/admin/users/' + userId, {
                    headers: { 'X-Admin-Token': currentSession.token }
                });
                const data = await res.json();
                title.innerText = `User Deep-Dive: ${data.user.name} (${data.user.id})`;

                content.innerHTML = `
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px;">
                        <div>
                            <p><strong>Email:</strong> ${data.user.email}</p>
                            <p><strong>Role:</strong> ${data.user.role} | <strong>Status:</strong> ${data.user.status}</p>
                            <p><strong>Total Requests:</strong> ${data.metrics.total_requests} (Last: ${data.metrics.last_active})</p>
                        </div>
                        <div>
                            <p><strong>Active API Keys:</strong> ${data.keys.length}</p>
                            <div style="font-family: monospace; font-size: 12px; margin-top: 4px;">
                                ${data.keys.map(k => `<div>• ${k.name}: <code>${k.key_prefix}</code></div>`).join('')}
                            </div>
                        </div>
                    </div>
                    <div style="margin-top: 14px;">
                        <h5 style="font-size: 13px; color: var(--text-muted); margin-bottom: 6px;">Stored Memory Facts (${data.memories_count})</h5>
                        <div class="memory-list" style="max-height: 200px;">
                            ${data.memories.length === 0 ? '<div style="color: var(--text-muted);">No memories stored for this user yet.</div>' : 
                                data.memories.map(m => `<div class="memory-item">${m.memory || JSON.stringify(m)}</div>`).join('')}
                        </div>
                    </div>
                `;
            } catch (err) {
                content.innerHTML = `<span style="color: var(--danger);">Error: ${err.message}</span>`;
            }
        }

        function closeUserInspector() {
            document.getElementById('admin-user-inspector').style.display = 'none';
        }

        async function toggleUserStatus(userId, newStatus) {
            try {
                const res = await fetch('/v1/admin/users/' + userId + '/status', {
                    method: 'PATCH',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Admin-Token': currentSession.token
                    },
                    body: JSON.stringify({ status: newStatus })
                });
                if (!res.ok) throw new Error('Status update failed.');
                loadAdminDashboard();
            } catch (err) {
                alert('Error: ' + err.message);
            }
        }

        async function deleteAdminUser(userId) {
            if (!confirm(`Are you sure you want to permanently delete user ${userId}? This will also wipe all their stored memories and API keys.`)) return;
            try {
                const res = await fetch('/v1/admin/users/' + userId, {
                    method: 'DELETE',
                    headers: { 'X-Admin-Token': currentSession.token }
                });
                if (!res.ok) throw new Error('User deletion failed.');
                loadAdminDashboard();
                closeUserInspector();
            } catch (err) {
                alert('Error: ' + err.message);
            }
        }
    </script>
</body>
</html>"""


# ============================================================
# Authentication Endpoints (Login, Sign-Up, Logout)
# ============================================================

@app.post("/v1/auth/signup", response_model=AuthResponse, tags=["Authentication"])
def signup(req: UserSignUpRequest):
    """
    Registers a new tenant user.
    Hashes password, automatically generates their isolated API key, and creates a 7-day session token.
    """
    try:
        user_data, raw_key = db.signup_user(name=req.name, email=req.email, password=req.password)
        token = create_user_session(user_data, raw_key)
        return AuthResponse(
            success=True,
            token=token,
            user=user_data,
            api_key=raw_key,
            message="User registered successfully. Keep your API key safe."
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Signup error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Registration failed.")


@app.post("/v1/auth/login", response_model=AuthResponse, tags=["Authentication"])
def login(req: UserLoginRequest):
    """
    Unified Authentication endpoint for both regular users and administrator.
    Validates credentials and returns session token + active API key.
    """
    result = db.authenticate_user(identifier=req.email, password=req.password)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password. Please verify your credentials."
        )

    user_data, active_key = result
    token = create_user_session(user_data, active_key)

    return AuthResponse(
        success=True,
        token=token,
        user=user_data,
        api_key=active_key,
        message="Authentication successful."
    )


@app.post("/v1/auth/logout", tags=["Authentication"])
def logout(user: Dict[str, Any] = Depends(verify_user_key)):
    """Logs out the active session."""
    return {"success": True, "message": "Logged out successfully."}


@app.get("/v1/auth/me", tags=["Authentication"])
def get_current_user(user: Dict[str, Any] = Depends(verify_user_key)):
    """Returns the profile and active API key of the authenticated session."""
    active_key = db.get_active_key_for_user(user["id"])
    return {
        "success": True,
        "user": user,
        "api_key": active_key
    }


@app.post("/v1/auth/keys/generate", response_model=ApiKeyResponse, tags=["Authentication"])
def generate_new_key(user: Dict[str, Any] = Depends(verify_user_key)):
    """Issues a new active API key for the authenticated user."""
    raw_key, rec = db.create_api_key(user_id=user["id"], name="Web Device Key")
    return ApiKeyResponse(
        success=True,
        api_key=raw_key,
        key_prefix=rec["key_prefix"],
        name=rec["name"]
    )


# ============================================================
# Admin Authentication & Telemetry Observability Endpoints
# ============================================================

@app.post("/v1/admin/login", response_model=AdminLoginResponse, tags=["Admin Observability"])
def admin_login(req: AdminLoginRequest):
    """
    Authenticate master administrator (default: admin / admin123).
    Returns a 24-hour admin session token.
    """
    token = verify_admin_credentials(req.username, req.password)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin username or password."
        )
    return AdminLoginResponse(
        success=True,
        token=token,
        expires_in_hours=24,
        message="Admin authentication successful."
    )


@app.get("/v1/admin/dashboard", response_model=AdminDashboardResponse, dependencies=[Depends(verify_admin)], tags=["Admin Observability"])
def admin_dashboard():
    """
    Returns global system metrics, all provisioned users, and recent request audit logs.
    """
    metrics = db.get_admin_dashboard_metrics()
    users_raw = db.list_users()

    # Enrich users with usage telemetry
    enriched_users = []
    for u in users_raw:
        if u["role"] == "admin":
            continue
        u_metrics = db.get_user_metrics(u["id"])
        enriched_users.append({
            **u,
            "total_requests": u_metrics["total_requests"],
            "last_active": u_metrics["last_active"]
        })

    recent_logs = db.get_all_usage_logs(limit=50)

    return AdminDashboardResponse(
        metrics=metrics,
        users=enriched_users,
        recent_logs=recent_logs
    )


@app.get("/v1/admin/users", response_model=List[Dict[str, Any]], dependencies=[Depends(verify_admin)], tags=["Admin Observability"])
def admin_list_users():
    """List all users with their usage counts and activity timestamps."""
    users_raw = db.list_users()
    enriched = []
    for u in users_raw:
        m = db.get_user_metrics(u["id"])
        enriched.append({**u, "total_requests": m["total_requests"], "last_active": m["last_active"]})
    return enriched


@app.post("/v1/admin/users", response_model=UserCreateResponse, dependencies=[Depends(verify_admin)], tags=["Admin Observability"])
def admin_create_user(req: UserCreateRequest):
    """
    Provision a new tenant user and automatically issue their unique API key.
    """
    try:
        user_data, raw_key = db.create_user(
            name=req.name,
            email=req.email,
            role=req.role or "user",
            password=req.password
        )
        return UserCreateResponse(
            success=True,
            user=user_data,
            api_key=raw_key
        )
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User creation failed: {str(e)}"
        )


@app.get("/v1/admin/users/{user_id}", response_model=AdminUserDetailResponse, dependencies=[Depends(verify_admin)], tags=["Admin Observability"])
def admin_get_user_detail(user_id: str):
    """
    Deep-dive: Inspect a specific user's memories, request logs, and active keys.
    """
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    keys = db.list_keys_for_user(user_id)
    metrics = db.get_user_metrics(user_id)
    memories = engine.get_all(user_id=user_id)

    return AdminUserDetailResponse(
        success=True,
        user=user,
        keys=keys,
        metrics=metrics,
        memories=memories,
        memories_count=len(memories)
    )


@app.patch("/v1/admin/users/{user_id}/status", dependencies=[Depends(verify_admin)], tags=["Admin Observability"])
def admin_update_user_status(user_id: str, req: UserStatusUpdateRequest):
    """Suspend or activate a user account."""
    if req.status not in ("active", "suspended"):
        raise HTTPException(status_code=400, detail="Status must be 'active' or 'suspended'.")
    db.update_user_status(user_id, req.status)
    return {"success": True, "message": f"User status updated to '{req.status}'."}


@app.delete("/v1/admin/users/{user_id}", dependencies=[Depends(verify_admin)], tags=["Admin Observability"])
def admin_delete_user(user_id: str):
    """Permanently delete a user account and wipe their memory partition."""
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    # Cascade wipe memories in vector store
    try:
        engine.delete_all(user_id=user_id)
    except Exception as e:
        logger.warning(f"Error wiping memories for {user_id}: {e}")

    db.delete_user(user_id)
    return {"success": True, "message": f"User '{user_id}' and all their data permanently deleted."}


@app.post("/v1/admin/users/{user_id}/keys", response_model=KeyCreateResponse, dependencies=[Depends(verify_admin)], tags=["Admin Observability"])
def admin_issue_key_for_user(user_id: str, req: KeyCreateRequest):
    """Issue an additional device API key for an existing user."""
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    raw_key, rec = db.create_api_key(user_id=user_id, name=req.name or "Client Device")
    return KeyCreateResponse(
        success=True,
        key_id=rec["id"],
        api_key=raw_key,
        key_prefix=rec["key_prefix"],
        name=rec["name"]
    )


@app.delete("/v1/admin/keys/{key_id}", dependencies=[Depends(verify_admin)], tags=["Admin Observability"])
def admin_revoke_key(key_id: str):
    """1-Click Revocation: Block an API key immediately."""
    db.revoke_key(key_id)
    return {"success": True, "message": f"API key '{key_id}' revoked."}


@app.get("/v1/admin/logs", dependencies=[Depends(verify_admin)], tags=["Admin Observability"])
def admin_get_audit_logs(limit: int = 100, user_id: Optional[str] = None):
    """View immutable request audit traces with filtering."""
    return db.get_all_usage_logs(limit=limit, user_id=user_id)


# ============================================================
# Core Intelligence Endpoints (Auto-Tenant Scoped)
# ============================================================

@app.post("/v1/recall", response_model=RecallResponse, tags=["Core Intelligence"])
def recall_memory(req: RecallRequest, user: Dict[str, Any] = Depends(verify_user_key)):
    """
    Semantic Memory Recall.
    Multi-signal hybrid retrieval automatically scoped to the authenticated user.
    """
    start_time = time.time()
    user_id = user["id"]
    try:
        result = engine.recall(
            query=req.query,
            user_id=user_id,
            agent_id=req.agent_id,
            top_k=req.top_k or 3,
        )
        latency = (time.time() - start_time) * 1000
        db.log_usage(user_id, "/v1/recall", "POST", 200, latency, f"Query: {req.query[:80]}")

        return RecallResponse(
            success=True,
            user_id=user_id,
            query=result["query"],
            memories=result["memories"],
            count=result["count"],
            raw=result.get("raw"),
        )
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        db.log_usage(user_id, "/v1/recall", "POST", 500, latency, f"Error: {str(e)[:80]}")
        logger.error(f"Error during memory recall for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Memory recall failed: {str(e)}")


@app.post("/v1/learn", response_model=LearnResponse, status_code=status.HTTP_202_ACCEPTED, tags=["Core Intelligence"])
def learn_memory(req: LearnRequest, background_tasks: BackgroundTasks, user: Dict[str, Any] = Depends(verify_user_key)):
    """
    Fire-and-Forget Memory Learning.
    Extracts atomic facts and persists into Supabase in the background.
    """
    start_time = time.time()
    user_id = user["id"]

    def _background_learn(message, uid, agent_id, metadata):
        try:
            engine.learn(message=message, user_id=uid, agent_id=agent_id, metadata=metadata)
        except Exception as err:
            logger.error(f"Background memory extraction failed for {uid}: {err}", exc_info=True)

    background_tasks.add_task(
        _background_learn,
        req.message,
        user_id,
        req.agent_id,
        req.metadata,
    )

    latency = (time.time() - start_time) * 1000
    db.log_usage(user_id, "/v1/learn", "POST", 202, latency, "Queued fact extraction")

    return LearnResponse(
        success=True,
        user_id=user_id,
        status="queued",
        message=f"Interaction queued for background fact extraction for user '{user_id}'."
    )


# ============================================================
# Profile Synthesis & Governance (Auto-Tenant Scoped)
# ============================================================

@app.get("/v1/profile", response_model=ProfileResponse, tags=["Profile & Governance"])
def get_user_profile(user: Dict[str, Any] = Depends(verify_user_key)):
    """Synthesize all memories into a consolidated User Profile summary."""
    user_id = user["id"]
    try:
        profile = engine.get_profile(user_id=user_id)
        db.log_usage(user_id, "/v1/profile", "GET", 200, 10.0, "Profile synthesized")
        return ProfileResponse(
            success=True,
            user_id=profile["user_id"],
            total_facts=profile["total_facts"],
            summary=profile["summary"],
            facts=profile["facts"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to synthesize profile: {str(e)}")


@app.get("/v1/memories", response_model=List[Dict[str, Any]], tags=["Profile & Governance"])
def list_all_memories(agent_id: Optional[str] = None, user: Dict[str, Any] = Depends(verify_user_key)):
    """Fetch all persistent memories stored for the authenticated user."""
    user_id = user["id"]
    db.log_usage(user_id, "/v1/memories", "GET", 200, 5.0, "List memories")
    return engine.get_all(user_id=user_id, agent_id=agent_id)


@app.delete("/v1/memories/{memory_id}", response_model=DeleteResponse, tags=["Profile & Governance"])
def delete_memory(memory_id: str, user: Dict[str, Any] = Depends(verify_user_key)):
    """Delete a specific memory fact by its UUID."""
    user_id = user["id"]
    engine.delete(memory_id=memory_id)
    db.log_usage(user_id, f"/v1/memories/{memory_id}", "DELETE", 200, 8.0, "Deleted fact")
    return DeleteResponse(success=True, message=f"Memory '{memory_id}' deleted successfully.")


@app.delete("/v1/users/reset", response_model=ResetResponse, tags=["Profile & Governance"])
def reset_my_memories(user: Dict[str, Any] = Depends(verify_user_key)):
    """1-Click Wipe Out: Permanently delete all memories for the authenticated user."""
    user_id = user["id"]
    engine.delete_all(user_id=user_id)
    db.log_usage(user_id, "/v1/users/reset", "DELETE", 200, 15.0, "Reset all memories")
    return ResetResponse(
        success=True,
        user_id=user_id,
        message=f"All long-term memories for user '{user_id}' have been permanently wiped."
    )


@app.get("/v1/export", response_model=ExportResponse, tags=["Backup & Portability"])
def export_memories(user: Dict[str, Any] = Depends(verify_user_key)):
    """Export all memories of the authenticated user as JSON backup."""
    user_id = user["id"]
    db.log_usage(user_id, "/v1/export", "GET", 200, 12.0, "Exported memories")
    return engine.export_memories(user_id=user_id)


@app.post("/v1/import", response_model=ImportResponse, tags=["Backup & Portability"])
def import_memories(req: ImportRequest, user: Dict[str, Any] = Depends(verify_user_key)):
    """Bulk import memories for the authenticated user."""
    user_id = user["id"]
    count = engine.import_memories(user_id=user_id, memories_list=req.memories)
    db.log_usage(user_id, "/v1/import", "POST", 200, 20.0, f"Imported {count} items")
    return ImportResponse(
        success=True,
        user_id=user_id,
        imported_count=count,
        message=f"Successfully imported {count} memories for user '{user_id}'."
    )


# ============================================================
# Monitoring & Health Endpoints
# ============================================================

@app.get("/health", response_model=HealthResponse, tags=["Monitoring"])
def health_check():
    """Public health check endpoint. Keeps Render active 24/7."""
    return HealthResponse(
        status="healthy",
        service="nova-cloud-brain",
        version="3.0.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/v1/stats", response_model=StatsResponse, tags=["Monitoring"])
def get_stats():
    """Infrastructure stats & telemetry."""
    return engine.get_stats()


# ============================================================
# Main Entry Point
# ============================================================

if __name__ == "__main__":
    import uvicorn
    key = get_or_generate_api_key()
    print("=" * 66)
    print(">>> NOVA MaaS v3.0 (Multi-Tenant & Admin Observability)")
    print(f"[*] Master API Key: {key}")
    print(f"[*] Admin Login:    Username: {ADMIN_USERNAME} | Password: {ADMIN_PASSWORD}")
    print("[*] Web Console:    http://localhost:8000")
    print("[*] API Docs:       http://localhost:8000/docs")
    print("=" * 66 + "\n")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
