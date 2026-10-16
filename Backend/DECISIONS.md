# DECISIONS.md

1. **Indexes.** `employees`: unique `emp_code` (no duplicate employees), `{department, emp_code}` (department filter and sort),
   `joined_on` (department summary headcount). `attendance_logs`: unique `{emp_code, date}` (one record per day, monthly
   summary, trend), `{date: -1, emp_code: 1}` (list sort, leaderboard month filter), `{status, date, emp_code}` (status filter),
   `{emp_code, punch_in: -1}` (punch-out finds the latest open record). I rejected a separate index on `date` alone,
   because `{date: -1, emp_code: 1}` already covers it.

2. **Punch-in race.** Both requests find the employee and build the same document. Both call `insert_one`. The unique index
   on `{emp_code, date}` lets MongoDB accept only the first one. The second gets a `DuplicateKeyError`, which I turn
   into 409. There is no "check first, then insert", so there is no gap between the check and the write.

3. **Ties.** I rank with `$rank` in `$setWindowFields`, so equal totals get the same rank and the next rank is skipped
   (1, 2, 2, 4). The `limit` filter is `rank <= limit` and runs after ranking, so everyone tied at the cutoff is returned,
   ordered by `emp_code`.

4. **Headcount.** The pipeline starts from `employees` (filtered by `joined_on <= last day of month`), not from the logs.
   It joins logs with `$lookup` and unwinds with `preserveNullAndEmptyArrays`, so an employee with no logs still produces
   one row and is counted.

5. **100x data.** I would store pre-computed daily or monthly totals per employee (updated on punch-out and PATCH), so the
   analytics read a small summary collection instead of scanning raw logs.
