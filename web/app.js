(() => {
  "use strict";

  const state = {
    user: null,
    health: null,
    deferredInstallPrompt: null,
    adminChats: [],
  };

  const $ = (id) => document.getElementById(id);

  // =========================================================================
  // PWA: Service Worker e instalación
  // =========================================================================
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    });
  }

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    state.deferredInstallPrompt = e;
    $("btn-install-cliente")?.classList.remove("hidden");
    $("btn-install-asesor")?.classList.remove("hidden");
  });

  async function triggerInstall() {
    if (!state.deferredInstallPrompt) return;
    state.deferredInstallPrompt.prompt();
    await state.deferredInstallPrompt.userChoice;
    state.deferredInstallPrompt = null;
    $("btn-install-cliente")?.classList.add("hidden");
    $("btn-install-asesor")?.classList.add("hidden");
  }

  $("btn-install-cliente")?.addEventListener("click", triggerInstall);
  $("btn-install-asesor")?.addEventListener("click", triggerInstall);

  // =========================================================================
  // Helpers de API y Markdown seguro (anti-XSS)
  // =========================================================================
  async function api(path, options = {}) {
    const res = await fetch(path, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || data.error || `Error HTTP ${res.status}`);
    }
    return data;
  }

  function escapeHtml(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatInline(text) {
    let out = escapeHtml(text);
    out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    return out;
  }

  function renderMarkdown(md) {
    const lines = String(md || "").split(/\r?\n/);
    let html = "";
    let inUl = false;
    let inOl = false;
    let inTable = false;

    const closeLists = () => {
      if (inUl) { html += "</ul>"; inUl = false; }
      if (inOl) { html += "</ol>"; inOl = false; }
    };
    const closeTable = () => {
      if (inTable) { html += "</tbody></table>"; inTable = false; }
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const trimmed = line.trim();

      if (!trimmed) {
        closeLists();
        closeTable();
        continue;
      }

      // Tablas Markdown
      if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
        closeLists();
        const cells = trimmed.slice(1, -1).split("|").map((c) => c.trim());
        const isSeparator = cells.every((c) => /^[-:]+$/.test(c));
        if (isSeparator) continue;
        if (!inTable) {
          inTable = true;
          html += "<table><thead><tr>" + cells.map((c) => `<th>${formatInline(c)}</th>`).join("") + "</tr></thead><tbody>";
        } else {
          html += "<tr>" + cells.map((c) => `<td>${formatInline(c)}</td>`).join("") + "</tr>";
        }
        continue;
      } else {
        closeTable();
      }

      if (trimmed.startsWith("### ")) {
        closeLists();
        html += `<h3>${formatInline(trimmed.slice(4))}</h3>`;
      } else if (trimmed.startsWith("## ")) {
        closeLists();
        html += `<h3>${formatInline(trimmed.slice(3))}</h3>`;
      } else if (trimmed.startsWith("> ")) {
        closeLists();
        html += `<blockquote>${formatInline(trimmed.slice(2))}</blockquote>`;
      } else if (/^[-*]\s+/.test(trimmed)) {
        if (inOl) { html += "</ol>"; inOl = false; }
        if (!inUl) { html += "<ul>"; inUl = true; }
        html += `<li>${formatInline(trimmed.replace(/^[-*]\s+/, ""))}</li>`;
      } else if (/^\d+\.\s+/.test(trimmed)) {
        if (inUl) { html += "</ul>"; inUl = false; }
        if (!inOl) { html += "<ol>"; inOl = true; }
        html += `<li>${formatInline(trimmed.replace(/^\d+\.\s+/, ""))}</li>`;
      } else {
        closeLists();
        html += `<p>${formatInline(trimmed)}</p>`;
      }
    }
    closeLists();
    closeTable();
    return html;
  }

  function formatMoney(v) {
    if (v === null || v === undefined || v === "") return "—";
    const num = Number(v);
    if (Number.isNaN(num)) return escapeHtml(v);
    return `S/ ${num.toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  function formatDateShort(iso) {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleString("es-PE", {
        day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
      });
    } catch {
      return iso;
    }
  }

  // =========================================================================
  // Salud e infraestructura
  // =========================================================================
  async function cargarHealth() {
    try {
      const h = await api("/health");
      state.health = h;
      const backendLabel = h.db_backend === "bigquery"
        ? `BigQuery (${h.gcp_project || "GCP"}:${h.dataset})`
        : "DuckDB Local";
      const aiLabel = h.ai_provider === "vertex_ai"
        ? `Vertex AI IAM (${h.gcp_location || "us-central1"} · ${h.modelo})`
        : h.modo_online
          ? `${h.modelo} (AI Studio)`
          : "Motor local (sin credenciales IA)";
      const ok = h.db && h.db.ok;

      $("infra-banner").innerHTML = `
        <span class="dot ${ok ? "dot-ok" : "dot-warn"}"></span>
        <span><strong>${escapeHtml(backendLabel)}</strong> · ${escapeHtml(aiLabel)}</span>
      `;
      const pillText = h.ai_provider === "vertex_ai"
        ? `${h.db_backend === "bigquery" ? "BigQuery" : "DuckDB"} · Vertex AI`
        : (h.db_backend === "bigquery" ? "BigQuery" : "DuckDB");
      $("cliente-backend-pill").textContent = pillText;
      $("asesor-backend-pill").textContent = pillText;
    } catch (err) {
      $("infra-banner").innerHTML = `<span class="dot dot-warn"></span><span>Sin conexión al servidor</span>`;
    }
  }

  // =========================================================================
  // Navegación entre vistas
  // =========================================================================
  function mostrarVista(nombre) {
    $("view-login").classList.toggle("hidden", nombre !== "login");
    $("view-cliente").classList.toggle("hidden", nombre !== "cliente");
    $("view-asesor").classList.toggle("hidden", nombre !== "asesor");
  }

  async function inicializarSesion() {
    await cargarHealth();
    try {
      const data = await api("/api/auth/me");
      state.user = data.usuario;
      if (state.user.rol === "cliente") {
        entrarPortalCliente();
      } else {
        entrarPortalAsesor();
      }
    } catch {
      mostrarVista("login");
    }
  }

  // =========================================================================
  // Login UI
  // =========================================================================
  document.querySelectorAll(".role-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".role-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const target = btn.dataset.target;
      $("form-cliente").classList.toggle("hidden", target !== "form-cliente");
      $("form-asesor").classList.toggle("hidden", target !== "form-asesor");
    });
  });

  document.querySelectorAll(".chip-demo").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("input-dni").value = btn.dataset.dni;
      $("input-nombre").value = btn.dataset.nombre;
    });
  });

  document.querySelectorAll(".chip-demo-asesor").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("input-asesor").value = btn.dataset.asesor;
    });
  });

  $("form-cliente").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = $("error-cliente");
    errEl.classList.add("hidden");
    const btn = $("btn-submit-cliente");
    btn.disabled = true;
    btn.textContent = "Validando...";
    try {
      const res = await api("/api/auth/cliente", {
        method: "POST",
        body: JSON.stringify({
          dni: $("input-dni").value.trim(),
          nombre_completo: $("input-nombre").value.trim(),
        }),
      });
      state.user = res.usuario;
      entrarPortalCliente();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove("hidden");
    } finally {
      btn.disabled = false;
      btn.textContent = "Ingresar al Portal Cliente";
    }
  });

  $("form-asesor").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = $("error-asesor");
    errEl.classList.add("hidden");
    const btn = $("btn-submit-asesor");
    btn.disabled = true;
    btn.textContent = "Validando...";
    try {
      const res = await api("/api/auth/asesor", {
        method: "POST",
        body: JSON.stringify({ identificador: $("input-asesor").value.trim() }),
      });
      state.user = res.usuario;
      entrarPortalAsesor();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove("hidden");
    } finally {
      btn.disabled = false;
      btn.textContent = "Ingresar al Panel Asesor / Admin";
    }
  });

  async function cerrarSesion() {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
    state.user = null;
    mostrarVista("login");
  }

  $("btn-logout-cliente").addEventListener("click", cerrarSesion);
  $("btn-logout-asesor").addEventListener("click", cerrarSesion);

  // =========================================================================
  // Renderizado de mensajes de chat (compartido Cliente / Asesor)
  // =========================================================================
  function appendMessage(container, { sender, text, herramientas, alertas, metricas }) {
    const div = document.createElement("div");
    div.className = `msg ${sender === "user" ? "msg-user" : "msg-bot"}`;

    if (sender === "user") {
      div.textContent = text;
    } else {
      let html = renderMarkdown(text);
      if (alertas && alertas.length > 0) {
        html += `<div class="msg-alert"><strong>🛡 Defensa activa:</strong> Se detectó y neutralizó un intento de Prompt Injection indirecto en datos no confiables.</div>`;
      }
      if ((herramientas && herramientas.length) || metricas) {
        const lat = metricas ? `${metricas.latencia_ms || 0} ms` : "";
        const tok = metricas ? `${metricas.tokens_totales || 0} tokens` : "";
        const cost = metricas ? `$${Number(metricas.costo_estimado_usd || 0).toFixed(5)}` : "";
        const traces = (herramientas || []).map((h) => {
          const argSummary = h.argumentos?.consulta_sql
            ? `SQL: ${h.argumentos.consulta_sql}`
            : h.argumentos?.consulta
              ? `Búsqueda (${h.argumentos.ramo || "todos"}): ${h.argumentos.consulta}`
              : JSON.stringify(h.argumentos || {});
          return `<div class="tool-trace-item"><strong>${escapeHtml(h.herramienta)}</strong> · ${escapeHtml(argSummary)}</div>`;
        }).join("");
        html += `
          <details class="msg-meta">
            <summary>Trazabilidad (${(herramientas || []).length} herramientas · ${lat} · ${tok} · ${cost})</summary>
            ${traces || "<p class='muted'>Sin herramientas invocadas.</p>"}
          </details>
        `;
      }
      div.innerHTML = html;
    }
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
  }

  async function enviarConsultaChat(inputEl, sendBtn, containerEl, textoOpcional = null) {
    const consulta = (textoOpcional !== null ? textoOpcional : inputEl.value).trim();
    if (!consulta) return;
    inputEl.value = "";
    sendBtn.disabled = true;

    appendMessage(containerEl, { sender: "user", text: consulta });
    const loadingDiv = appendMessage(containerEl, {
      sender: "bot",
      text: "*Consultando pólizas, siniestros y condicionados...*",
    });

    try {
      const res = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({ consulta }),
      });
      loadingDiv.remove();
      appendMessage(containerEl, {
        sender: "bot",
        text: res.respuesta,
        herramientas: res.herramientas_usadas,
        alertas: res.alertas_seguridad,
        metricas: res.metricas,
      });
      if (state.user?.rol === "asesor") {
        cargarDatosAdmin();
      }
    } catch (err) {
      loadingDiv.remove();
      appendMessage(containerEl, {
        sender: "bot",
        text: `**Error al procesar la consulta:** ${err.message}`,
      });
    } finally {
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  // =========================================================================
  // PORTAL CLIENTE
  // =========================================================================
  async function entrarPortalCliente() {
    mostrarVista("cliente");
    const u = state.user;
    $("cliente-subtitulo").textContent = `${u.nombre} · ${u.usuario_id}`;
    $("cliente-perfil-card").innerHTML = `
      <strong>${escapeHtml(u.nombre)}</strong><br/>
      <span class="muted">ID: ${escapeHtml(u.usuario_id)} · DNI: ${escapeHtml(u.dni)}</span><br/>
      <span class="muted">${escapeHtml(u.distrito || "")} · ${escapeHtml(u.email || "")}</span>
    `;

    const msgBox = $("cliente-messages");
    msgBox.innerHTML = "";
    appendMessage(msgBox, {
      sender: "bot",
      text: `Hola **${u.nombre}**, soy el Asistente Virtual de **Seguros Horizonte S.A.**\n\nTu sesión está autenticada y protegida con aislamiento de privacidad para el titular \`${u.usuario_id}\`. ¿En qué te ayudo hoy con tus pólizas o siniestros?`,
    });

    // Cargar resumen e historial en paralelo
    try {
      const [resumen, historial] = await Promise.all([
        api("/api/cliente/resumen"),
        api("/api/cliente/historial?limite=20"),
      ]);
      renderResumenCliente(resumen);
      (historial.mensajes || []).forEach((m) => {
        appendMessage(msgBox, { sender: "user", text: m.consulta });
        appendMessage(msgBox, {
          sender: "bot",
          text: m.respuesta,
          herramientas: m.herramientas_usadas,
          alertas: m.alertas_seguridad,
          metricas: m.metricas,
        });
      });
    } catch (err) {
      $("lista-polizas").innerHTML = `<p class="muted">No se pudo cargar el resumen: ${escapeHtml(err.message)}</p>`;
    }
  }

  function renderResumenCliente(resumen) {
    const polizas = resumen.polizas || [];
    const siniestros = resumen.siniestros || [];

    $("lista-polizas").innerHTML = polizas.length
      ? polizas.map((p) => {
          const pill = p.estado === "vigente" ? "pill-ok" : "pill-danger";
          return `
            <div class="mini-card" data-ask="Dame el detalle y coberturas de mi póliza ${escapeHtml(p.poliza_id)}">
              <div class="mini-card-head">
                <strong>${escapeHtml(p.poliza_id)} · ${escapeHtml(p.producto)}</strong>
                <span class="pill ${pill}">${escapeHtml(p.estado)}</span>
              </div>
              <div class="muted">Ramo: ${escapeHtml(p.ramo)} ${p.placa_vehiculo ? `· Placa ${escapeHtml(p.placa_vehiculo)}` : ""}</div>
              <div class="muted">Suma: ${formatMoney(p.suma_asegurada_soles)} · Deducible: ${formatMoney(p.deducible_soles)}</div>
              <div class="muted">Vigencia: ${escapeHtml(p.fecha_inicio)} al ${escapeHtml(p.fecha_fin)}</div>
            </div>
          `;
        }).join("")
      : `<p class="muted">Sin pólizas registradas.</p>`;

    $("lista-siniestros").innerHTML = siniestros.length
      ? siniestros.map((s) => {
          const pill = s.estado === "pagado" || s.estado === "aprobado"
            ? "pill-ok"
            : s.estado === "rechazado"
              ? "pill-danger"
              : "pill-warn";
          return `
            <div class="mini-card" data-ask="¿Cuál es el estado actual de mi siniestro ${escapeHtml(s.siniestro_id)}?">
              <div class="mini-card-head">
                <strong>${escapeHtml(s.siniestro_id)} · ${escapeHtml(s.tipo_evento)}</strong>
                <span class="pill ${pill}">${escapeHtml(s.estado)}</span>
              </div>
              <div class="muted">Póliza ${escapeHtml(s.poliza_id)} · Ocurrencia: ${escapeHtml(s.fecha_ocurrencia)}</div>
              <div class="muted">Reclamado: ${formatMoney(s.monto_reclamado_soles)}</div>
            </div>
          `;
        }).join("")
      : `<p class="muted">No registras siniestros.</p>`;

    document.querySelectorAll("#cliente-sidebar .mini-card").forEach((card) => {
      card.addEventListener("click", () => {
        $("cliente-sidebar").classList.remove("open");
        enviarConsultaChat(
          $("cliente-chat-input"),
          $("cliente-send-btn"),
          $("cliente-messages"),
          card.dataset.ask
        );
      });
    });
  }

  $("btn-toggle-sidebar")?.addEventListener("click", () => {
    $("cliente-sidebar").classList.toggle("open");
  });
  $("btn-close-sidebar")?.addEventListener("click", () => {
    $("cliente-sidebar").classList.remove("open");
  });

  $("cliente-chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    enviarConsultaChat($("cliente-chat-input"), $("cliente-send-btn"), $("cliente-messages"));
  });

  $("cliente-chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      $("cliente-chat-form").requestSubmit();
    }
  });

  document.querySelectorAll(".prompt-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      enviarConsultaChat(
        $("cliente-chat-input"),
        $("cliente-send-btn"),
        $("cliente-messages"),
        chip.dataset.prompt
      );
    });
  });

  // =========================================================================
  // PORTAL ASESOR / ADMIN
  // =========================================================================
  async function entrarPortalAsesor() {
    mostrarVista("asesor");
    const u = state.user;
    $("asesor-subtitulo").textContent = `${u.nombre} (${u.usuario_id}) · Acceso global`;

    const msgBox = $("asesor-messages");
    if (!msgBox.children.length) {
      appendMessage(msgBox, {
        sender: "bot",
        text: `Bienvenido/a **${u.nombre}** (\`${u.usuario_id}\`). Estás en modo **Asesor Comercial**, con autorización para consultas agregadas y revisión de cualquier cliente o siniestro.`,
      });
    }
    await cargarDatosAdmin();
  }

  async function cargarDatosAdmin() {
    const params = new URLSearchParams({ limite: "120" });
    const rol = $("filtro-rol").value;
    const uid = $("filtro-usuario").value.trim();
    const buscar = $("filtro-buscar").value.trim();
    const alertas = $("filtro-alertas").checked;
    if (rol) params.set("rol", rol);
    if (uid) params.set("usuario_id", uid);
    if (buscar) params.set("buscar", buscar);
    if (alertas) params.set("solo_alertas", "true");

    try {
      const [mRes, cRes, tRes] = await Promise.all([
        api("/api/admin/metricas"),
        api(`/api/admin/chats?${params.toString()}`),
        api("/api/admin/tickets?limite=100"),
      ]);
      renderKpis(mRes.metricas);
      state.adminChats = cRes.chats || [];
      renderChatsAdmin(state.adminChats);
      renderTicketsAdmin(tRes.tickets || []);
    } catch (err) {
      $("lista-chats-admin").innerHTML = `<p class="muted">Error al cargar datos: ${escapeHtml(err.message)}</p>`;
    }
  }

  function renderKpis(m) {
    $("kpi-total").textContent = m.total_interacciones ?? 0;
    $("kpi-clientes").textContent = m.clientes_atendidos ?? 0;
    $("kpi-tickets").textContent = m.total_tickets ?? 0;
    $("kpi-alertas").textContent = m.alertas_seguridad_detectadas ?? 0;
    $("kpi-latencia").textContent = `${m.latencia_promedio_ms ?? 0} ms`;
    $("kpi-costo").textContent = `$${Number(m.costo_total_usd || 0).toFixed(4)}`;
  }

  function renderChatsAdmin(chats) {
    const listEl = $("lista-chats-admin");
    if (!chats.length) {
      listEl.innerHTML = `<p class="muted">No hay conversaciones que coincidan con los filtros.</p>`;
      $("detalle-chat-admin").innerHTML = `<p class="muted">Sin registros para mostrar.</p>`;
      return;
    }

    listEl.innerHTML = chats.map((c, idx) => {
      const sesion = c.usuario_sesion || {};
      const hasAlert = (c.alertas_seguridad || []).length > 0;
      return `
        <div class="audit-item ${hasAlert ? "has-alert" : ""}" data-idx="${idx}">
          <div class="audit-item-top">
            <span>
              <span class="pill ${sesion.rol === "cliente" ? "pill-ok" : "pill-neutral"}">${escapeHtml(sesion.rol)}</span>
              <strong>${escapeHtml(sesion.usuario_id)}</strong>
              ${hasAlert ? `<span class="pill pill-danger">⚠ Prompt Injection</span>` : ""}
            </span>
            <span class="muted">${escapeHtml(formatDateShort(c.timestamp_utc))}</span>
          </div>
          <div class="audit-item-q">${escapeHtml(c.consulta)}</div>
        </div>
      `;
    }).join("");

    listEl.querySelectorAll(".audit-item").forEach((el) => {
      el.addEventListener("click", () => {
        listEl.querySelectorAll(".audit-item").forEach((x) => x.classList.remove("selected"));
        el.classList.add("selected");
        renderDetalleChatAdmin(chats[Number(el.dataset.idx)]);
      });
    });

    // Seleccionar el primero automáticamente
    listEl.querySelector(".audit-item")?.click();
  }

  function renderDetalleChatAdmin(c) {
    if (!c) return;
    const sesion = c.usuario_sesion || {};
    const m = c.metricas || {};
    const alertas = c.alertas_seguridad || [];
    const herramientas = c.herramientas_usadas || [];

    $("detalle-chat-admin").innerHTML = `
      <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; margin-bottom:10px;">
        <div>
          <span class="pill ${sesion.rol === "cliente" ? "pill-ok" : "pill-neutral"}">${escapeHtml(sesion.rol)}</span>
          <strong>${escapeHtml(sesion.usuario_id)}</strong>
          ${c.caso_id ? `<span class="pill pill-neutral">${escapeHtml(c.caso_id)}</span>` : ""}
        </div>
        <span class="muted">${escapeHtml(c.timestamp_utc || "")}</span>
      </div>

      ${alertas.length ? `<div class="msg-alert"><strong>🛡 Alerta de Seguridad:</strong><br/>${alertas.map(escapeHtml).join("<br/>")}</div>` : ""}

      <h4 style="margin:12px 0 4px;">Consulta del usuario</h4>
      <div class="tool-trace-item" style="font-family:inherit; font-size:0.9rem;">${escapeHtml(c.consulta)}</div>

      <h4 style="margin:14px 0 4px;">Respuesta del Asistente</h4>
      <div class="msg-bot" style="max-width:100%; border-radius:10px; padding:12px;">${renderMarkdown(c.respuesta)}</div>

      <h4 style="margin:14px 0 4px;">Herramientas invocadas (${herramientas.length})</h4>
      ${herramientas.map((h) => `<div class="tool-trace-item">${escapeHtml(JSON.stringify(h, null, 2))}</div>`).join("") || "<p class='muted'>Ninguna</p>"}

      <div class="muted" style="margin-top:12px;">
        Modelo: <strong>${escapeHtml(m.modelo || "—")}</strong> ·
        Latencia: <strong>${m.latencia_ms ?? 0} ms</strong> ·
        Tokens: <strong>${m.tokens_totales ?? 0}</strong> ·
        Costo: <strong>$${Number(m.costo_estimado_usd || 0).toFixed(6)}</strong>
      </div>
    `;
  }

  function renderTicketsAdmin(tickets) {
    const el = $("lista-tickets-admin");
    if (!tickets.length) {
      el.innerHTML = `<p class="muted">No hay tickets de escalamiento registrados todavía.</p>`;
      return;
    }
    el.innerHTML = tickets.map((t) => {
      const sesion = t.sesion_usuario || {};
      return `
        <div class="ticket-card">
          <div class="mini-card-head">
            <h4>${escapeHtml(t.ticket_id)}</h4>
            <span class="pill pill-warn">${escapeHtml(t.estado_ticket || "abierto")}</span>
          </div>
          <div class="muted" style="margin-bottom:6px;">
            Usuario: <strong>${escapeHtml(sesion.usuario_id)}</strong> (${escapeHtml(sesion.rol)}) ·
            Área: <strong>${escapeHtml(t.area_destino)}</strong>
          </div>
          <p style="margin:0 0 6px;"><strong>Motivo:</strong> ${escapeHtml(t.motivo_escalamiento)}</p>
          <p class="muted" style="margin:0 0 6px;">${escapeHtml(t.resumen_caso)}</p>
          <div class="muted">${escapeHtml(formatDateShort(t.timestamp_creacion_utc))}</div>
        </div>
      `;
    }).join("");
  }

  document.querySelectorAll(".admin-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".admin-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const panelId = tab.dataset.panel;
      document.querySelectorAll(".admin-panel").forEach((p) => {
        p.classList.toggle("hidden", p.id !== panelId);
      });
    });
  });

  $("btn-aplicar-filtros").addEventListener("click", cargarDatosAdmin);
  $("btn-refresh-admin").addEventListener("click", cargarDatosAdmin);
  $("filtro-buscar").addEventListener("keydown", (e) => {
    if (e.key === "Enter") cargarDatosAdmin();
  });

  $("asesor-chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    enviarConsultaChat($("asesor-chat-input"), $("asesor-send-btn"), $("asesor-messages"));
  });

  $("asesor-chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      $("asesor-chat-form").requestSubmit();
    }
  });

  document.querySelectorAll(".prompt-chip-asesor").forEach((chip) => {
    chip.addEventListener("click", () => {
      enviarConsultaChat(
        $("asesor-chat-input"),
        $("asesor-send-btn"),
        $("asesor-messages"),
        chip.dataset.prompt
      );
    });
  });

  // Arranque
  inicializarSesion();
})();
