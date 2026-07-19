/* CX Season Planner — rendering, sort/filter, stars.
   Data comes from js/race-data.js (const RACE_DATA), regenerated daily. */

(function () {
  "use strict";

  const STORAGE_KEY = "cx-starred";

  const state = {
    sort: "date", // "date" | "drive"
    maxDrive: null, // minutes, or null for any
    hideClosed: false,
    starredOnly: false,
    starred: loadStarred(),
    expanded: new Set(), // race ids with categories open
  };

  const listEl = document.getElementById("race-list");

  // --- Persistence -----------------------------------------------------------

  function loadStarred() {
    try {
      return new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"));
    } catch {
      return new Set();
    }
  }

  function saveStarred() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...state.starred]));
  }

  // --- Formatting ------------------------------------------------------------

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  // Parse "YYYY-MM-DD" as a local date (new Date(str) would treat it as UTC).
  function localDate(isoDay) {
    const [year, month, day] = isoDay.split("-").map(Number);
    return new Date(year, month - 1, day);
  }

  function pluralize(count, singular, plural) {
    return count === 1 ? singular : plural;
  }

  // Defense in depth: the fetch script already drops non-https URLs, but this
  // value lands in an href, so never trust it blindly.
  function safeUrl(url) {
    return url && url.startsWith("https://") ? url : null;
  }

  const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"];

  function formatDrive(minutes) {
    if (minutes == null) return "—";
    const hours = Math.floor(minutes / 60);
    const mins = Math.round(minutes % 60);
    return hours ? `${hours}h ${String(mins).padStart(2, "0")}m` : `${mins}m`;
  }

  function formatShortDate(date) {
    return `${MONTHS[date.getMonth()].slice(0, 3)} ${date.getDate()}`;
  }

  function formatStartTime(hms) {
    if (!hms) return "";
    const [hours, minutes] = hms.split(":").map(Number);
    const meridiem = hours >= 12 ? "pm" : "am";
    const displayHours = hours % 12 || 12;
    return minutes ? `${displayHours}:${String(minutes).padStart(2, "0")}${meridiem}` : `${displayHours}${meridiem}`;
  }

  // --- Google Calendar link --------------------------------------------------

  // Prefilled all-day event: opens GCal with name/dates/location/details set,
  // Mark just hits Save. GCal's all-day range is end-exclusive, so a 1-day
  // race on 9/5 is 20260905/20260906 and a 9/5-9/6 weekend is /20260907.
  function calendarUrl(race) {
    const compact = (date) =>
      `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, "0")}${String(date.getDate()).padStart(2, "0")}`;
    const endExclusive = localDate(race.endDate);
    endExclusive.setDate(endExclusive.getDate() + 1);
    const location = [race.city, race.state].filter(Boolean).join(", ");
    const teaser = race.categories.slice(0, 3).map((cat) => cat.name).join(", ");
    const registerUrl = safeUrl(race.url);
    const details = [
      registerUrl ? `Register: ${registerUrl}` : "",
      race.categories.length
        ? `${race.categories.length} ${pluralize(race.categories.length, "category", "categories")}${teaser ? ` — ${teaser}` : ""}${race.categories.length > 3 ? ", …" : ""}`
        : "",
    ].filter(Boolean).join("\n");
    const params = new URLSearchParams({
      action: "TEMPLATE",
      text: race.name,
      dates: `${compact(localDate(race.startDate))}/${compact(endExclusive)}`,
      location,
      details,
    });
    return `https://calendar.google.com/calendar/render?${params}`;
  }

  // --- Registration status (computed live, so badges never go stale) --------

  function regStatus(race, now) {
    const opens = race.regOpen ? new Date(race.regOpen) : null;
    const closes = race.regClose ? new Date(race.regClose) : null;
    if (opens && now < opens) {
      return { kind: "upcoming", label: `Opens ${formatShortDate(opens)}`, detail: "" };
    }
    if (closes && now > closes) {
      return { kind: "closed", label: "Closed", detail: "" };
    }
    return {
      kind: "open",
      label: "Reg open",
      detail: closes ? `closes ${formatShortDate(closes)}` : "no close date listed",
    };
  }

  // --- Filtering + sorting ---------------------------------------------------

  function visibleRaces() {
    const now = new Date();
    let races = RACE_DATA.events.filter((race) => {
      if (state.maxDrive != null && (race.driveMinutes == null || race.driveMinutes > state.maxDrive)) return false;
      if (state.hideClosed && regStatus(race, now).kind === "closed") return false;
      if (state.starredOnly && !state.starred.has(race.id)) return false;
      return true;
    });
    if (state.sort === "drive") {
      const byDate = (a, b) => (a.startDate < b.startDate ? -1 : a.startDate > b.startDate ? 1 : 0);
      races = [...races].sort((a, b) => {
        if (a.driveMinutes == null && b.driveMinutes == null) return byDate(a, b);
        if (a.driveMinutes == null) return 1;
        if (b.driveMinutes == null) return -1;
        return a.driveMinutes - b.driveMinutes || byDate(a, b);
      });
    }
    return races;
  }

  // --- Rendering -------------------------------------------------------------

  function proximityClass(race) {
    if (race.driveMinutes == null) return "far";
    if (race.driveMinutes < 120) return "near";
    if (race.driveMinutes <= 240) return "";
    return "far";
  }

  function raceHtml(race, index, now) {
    const start = localDate(race.startDate);
    const end = localDate(race.endDate);
    const multiDay = race.days > 1;
    const dow = multiDay ? `${DOW[start.getDay()]}–${DOW[end.getDay()]}` : DOW[start.getDay()];
    const status = regStatus(race, now);
    const starred = state.starred.has(race.id);
    const location = [race.city, race.state].filter(Boolean).join(", ");
    const catCount = race.categories.length;
    const estimate = race.driveSource === "estimate";

    const categories = catCount
      ? `<details class="race-cats" data-id="${race.id}"${state.expanded.has(race.id) ? " open" : ""}>
          <summary>${catCount} ${pluralize(catCount, "category", "categories")}</summary>
          <div class="cat-table">${race.categories.map((cat) => `
            <div class="cat-row">
              <span class="cat-name" title="${escapeHtml(cat.name)}">${escapeHtml(cat.name)}</span>
              <span class="cat-info">${[formatStartTime(cat.startTime), cat.fee != null ? `$${cat.fee}` : ""].filter(Boolean).join(" · ")}</span>
            </div>`).join("")}
          </div>
        </details>`
      : "";

    return `
    <article class="race ${proximityClass(race)}" style="--i:${Math.min(index, 20)}">
      <div class="race-date">
        <span class="dow">${dow}</span>
        <span class="day">${formatShortDate(start)}</span>
        ${multiDay ? `<span class="badge-days">${race.days} days</span>` : ""}
      </div>
      <div class="race-main">
        <h3 class="race-name">${safeUrl(race.url)
          ? `<a href="${escapeHtml(safeUrl(race.url))}" rel="noopener">${escapeHtml(race.name)}</a>`
          : escapeHtml(race.name)}</h3>
        <p class="race-meta">${escapeHtml(location)}${race.presentedBy ? `<span class="sep">·</span>${escapeHtml(race.presentedBy)}` : ""}</p>
        <div class="race-reg">
          <span class="badge ${status.kind}">${status.label}</span>
          ${status.detail ? `<span class="reg-detail">${status.detail}</span>` : ""}
        </div>
        ${categories}
      </div>
      <div class="race-drive ${race.driveMinutes == null ? "none" : ""}" title="${estimate ? "Straight-line estimate (routing unavailable)" : "Typical drive from Brooklyn"}">
        <span class="drive-time">${formatDrive(race.driveMinutes)}</span>
        ${race.driveMiles != null ? `<span class="drive-miles">${race.driveMiles} mi</span>` : ""}
        ${estimate ? `<span class="est">estimate</span>` : ""}
      </div>
      <div class="race-actions">
        <button type="button" class="star-btn ${starred ? "is-starred" : ""}" data-id="${race.id}"
          aria-pressed="${starred}" aria-label="${starred ? "Unstar" : "Star"} ${escapeHtml(race.name)}"
          title="${starred ? "Remove from" : "Add to"} races I'm considering">${starred ? "★" : "☆"}</button>
        <a class="cal-link" href="${escapeHtml(calendarUrl(race))}" target="_blank" rel="noopener"
          title="Add to Google Calendar">+ Cal</a>
      </div>
    </article>`;
  }

  function emptyStateHtml() {
    const suggestions = [];
    if (state.starredOnly && state.starred.size === 0) suggestions.push("you haven't starred any races yet — hit the ☆ on races you're considering");
    if (state.maxDrive != null) suggestions.push("widen the drive-time range");
    if (state.hideClosed) suggestions.push("include closed registrations");
    if (state.starredOnly && state.starred.size > 0) suggestions.push("turn off “Starred only”");
    return `
    <div class="empty-state">
      <span class="empty-mark" aria-hidden="true">🥶</span>
      <h2>No races match</h2>
      <p>${suggestions.length ? `Try: ${suggestions.join(", or ")}.` : "The season data may still be filling in — organizers post through the summer."}</p>
    </div>`;
  }

  function render() {
    const now = new Date();
    const races = visibleRaces();

    if (!races.length) {
      listEl.innerHTML = emptyStateHtml();
      updateMasthead(races);
      return;
    }

    if (state.sort === "drive") {
      // Flat proximity-ordered list, no month grouping.
      listEl.innerHTML = races.map((race, i) => raceHtml(race, i, now)).join("");
    } else {
      const groups = new Map();
      for (const race of races) {
        const start = localDate(race.startDate);
        const key = `${MONTHS[start.getMonth()]} ${start.getFullYear()}`;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(race);
      }
      let index = 0;
      listEl.innerHTML = [...groups.entries()].map(([month, monthRaces]) => `
        <section>
          <h2 class="month-heading">${month} <span class="month-count">${monthRaces.length} ${pluralize(monthRaces.length, "race", "races")}</span></h2>
          ${monthRaces.map((race) => raceHtml(race, index++, now)).join("")}
        </section>`).join("");
    }
    updateMasthead(races);
  }

  function updateMasthead(visible) {
    const total = RACE_DATA.events.length;
    const shown = visible.length === total ? `${total} races` : `${visible.length} of ${total} races`;
    document.getElementById("masthead-sub").textContent =
      `${shown} on the calendar · drive times from ${RACE_DATA.origin.label} · data refreshed ${relativeTime(RACE_DATA.generatedAt)}`;
    document.getElementById("footer-generated").textContent =
      `data refreshed ${new Date(RACE_DATA.generatedAt).toLocaleString()}`;
  }

  function relativeTime(iso) {
    const days = Math.round((Date.now() - new Date(iso).getTime()) / 86400000);
    if (days <= 0) return "today";
    if (days === 1) return "yesterday";
    return `${days} days ago`;
  }

  // --- Events ----------------------------------------------------------------

  function wireSegmented(containerId, apply) {
    const container = document.getElementById(containerId);
    container.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button) return;
      for (const sibling of container.querySelectorAll("button")) {
        sibling.classList.toggle("is-active", sibling === button);
        sibling.setAttribute("aria-pressed", String(sibling === button));
      }
      apply(button);
      render();
    });
  }

  wireSegmented("sort-control", (button) => { state.sort = button.dataset.sort; });
  wireSegmented("drive-control", (button) => {
    state.maxDrive = button.dataset.max === "" ? null : Number(button.dataset.max);
  });

  document.getElementById("hide-closed").addEventListener("change", (event) => {
    state.hideClosed = event.target.checked;
    render();
  });

  document.getElementById("starred-only").addEventListener("change", (event) => {
    state.starredOnly = event.target.checked;
    render();
  });

  listEl.addEventListener("click", (event) => {
    const starButton = event.target.closest(".star-btn");
    if (!starButton) return;
    const id = Number(starButton.dataset.id);
    if (state.starred.has(id)) state.starred.delete(id);
    else state.starred.add(id);
    saveStarred();
    render();
  });

  // Remember which category lists are open across re-renders.
  listEl.addEventListener("toggle", (event) => {
    const details = event.target.closest(".race-cats");
    if (!details) return;
    const id = Number(details.dataset.id);
    if (details.open) state.expanded.add(id);
    else state.expanded.delete(id);
  }, true);

  render();
})();
