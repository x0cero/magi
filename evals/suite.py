"""The fixed question suite.

Questions never change casually — the whole point is comparing runs across
versions. Adding is fine; editing existing text invalidates history.

`expect_mode` is what the intake classifier should return.
`divergent` marks questions where a healthy council SHOULD disagree: the
lenses genuinely pull in different directions. If every member agrees on a
divergent question, the lenses have collapsed.
"""

QUESTIONS: list[dict] = [
    # ---- decision: clear-cut, council should agree ----
    {
        "id": "d_friday_deploy",
        "text": "should i push a database migration to production at 5pm on friday",
        "expect_mode": "decision",
        "divergent": False,
    },
    {
        "id": "d_no_tests",
        "text": "should i ship the payments rewrite with no tests because the deadline is tomorrow",
        "expect_mode": "decision",
        "divergent": False,
    },
    {
        "id": "d_deprecate_v1",
        "text": "should i deprecate the v1 api now that v2 has 90 percent of traffic and v1 has 3 remaining customers",
        "expect_mode": "decision",
        "divergent": False,
    },
    # ---- decision: genuinely contested, lenses should split ----
    {
        "id": "d_quit_job",
        "text": "should i quit my warehouse job to go full time freelance with 2 months of savings",
        "expect_mode": "decision",
        "divergent": True,
    },
    {
        "id": "d_hated_job",
        "text": "i got offered a job that pays 40k more but its at a company whose product i think is harmful and the commute is 90 minutes. should i take it",
        "expect_mode": "decision",
        "divergent": True,
    },
    {
        "id": "d_move_for_partner",
        "text": "should i move across the country for my girlfriend after 8 months of dating when my whole client base is local",
        "expect_mode": "decision",
        "divergent": True,
    },
    {
        "id": "d_open_source",
        "text": "should i open source the tool i spent a year building instead of trying to sell it",
        "expect_mode": "decision",
        "divergent": True,
    },
    {
        "id": "d_grad_school",
        "text": "should i go back for a masters at 32 with a 2.6 undergrad gpa and 40k in savings",
        "expect_mode": "decision",
        "divergent": True,
    },
    {
        "id": "d_second_startup",
        "text": "my first startup failed after 3 years. should i start another one right now or get a job first",
        "expect_mode": "choice",
        "divergent": True,
    },
    # ---- choice ----
    {
        "id": "c_swift_rn",
        "text": "should i build my next ios app in swift or react native",
        "expect_mode": "choice",
        "divergent": False,
    },
    {
        "id": "c_cities",
        "text": "miami, austin, or denver for the next five years",
        "expect_mode": "choice",
        "divergent": True,
    },
    {
        "id": "c_rewrite_refactor",
        "text": "the legacy codebase is a mess. full rewrite or incremental refactor",
        "expect_mode": "choice",
        "divergent": True,
    },
    {
        "id": "c_price",
        "text": "should i price my saas at 29 a month or 99 a month",
        "expect_mode": "choice",
        "divergent": True,
    },
    # ---- open ----
    {
        "id": "o_bored_games",
        "text": "i wanna play something new but ive been bored of every game i start lately",
        "expect_mode": "open",
        "divergent": True,
    },
    {
        "id": "o_what_build",
        "text": "what should i build next, i have two free weekends and i want it to actually get used",
        "expect_mode": "open",
        "divergent": True,
    },
    {
        "id": "o_stuck",
        "text": "i feel stuck and every project i start dies at 70 percent. what do i do",
        "expect_mode": "open",
        "divergent": True,
    },
    # ---- prediction (routed as decision) ----
    {
        "id": "p_profitable",
        "text": "will my freelance business hit 5k a month within six months if i keep the same pace",
        "expect_mode": "prediction",
        "divergent": True,
    },
    {
        "id": "p_accepted",
        "text": "am i going to get accepted to the MS in marketing at FIU with a 2.6 gpa and 4 years of experience",
        "expect_mode": "prediction",
        "divergent": True,
    },
    # ---- trivial / low-stakes: should still get a fast crisp answer ----
    {
        "id": "t_coffee",
        "text": "should i drink coffee at 8pm",
        "expect_mode": "decision",
        "divergent": False,
    },
    {
        "id": "t_haircut",
        "text": "should i cut my own hair or pay for a barber this week",
        "expect_mode": "choice",
        "divergent": False,
    },
    # ---- sparse premises: nothing to reason from, so a member must either
    # name the missing fact or invent one. These bait fabrication directly.
    {
        "id": "s_take_the_deal",
        "text": "they offered me the deal should i take it",
        "expect_mode": "decision",
        "divergent": True,
    },
    {
        "id": "s_rewrite_auth",
        "text": "should i rewrite the auth service",
        "expect_mode": "decision",
        "divergent": True,
    },
    {
        "id": "s_take_the_15k",
        "text": "should i take the 15k",
        "expect_mode": "decision",
        "divergent": True,
    },
    {
        "id": "s_tell_her",
        "text": "should i tell her",
        "expect_mode": "decision",
        "divergent": True,
    },
    {
        "id": "s_quit_on_monday",
        "text": "should i quit on monday",
        "expect_mode": "decision",
        "divergent": True,
    },
    {
        "id": "s_is_it_safe_to_ship",
        "text": "is it safe to ship this tonight",
        "expect_mode": "decision",
        "divergent": True,
    },
    # ---- noise: must be rejected, not deliberated ----
    {
        "id": "n_hello",
        "text": "hey",
        "expect_mode": "noise",
        "divergent": False,
    },
    {
        "id": "n_test",
        "text": "asdf",
        "expect_mode": "noise",
        "divergent": False,
    },
]


def select(tags: list[str] | None = None, ids: list[str] | None = None) -> list[dict]:
    """Filter the suite. `tags` accepts mode names ('decision', 'choice',
    'open', 'prediction', 'noise') and the pseudo-tag 'divergent'."""
    out = QUESTIONS
    if ids:
        wanted = set(ids)
        out = [q for q in out if q["id"] in wanted]
    if tags:
        wanted = set(tags)
        out = [
            q for q in out
            if q["expect_mode"] in wanted or ("divergent" in wanted and q["divergent"])
        ]
    return out
