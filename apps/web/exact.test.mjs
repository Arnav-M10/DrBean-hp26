import assert from "node:assert/strict";
import test from "node:test";
import { compareExact, parseExact, parseMeasurementsCsv, validateMeasurements } from "./exact.mjs";

test("canonicalizes finite decimals and fractions without floating-point rounding", () => {
  assert.equal(parseExact(" +000.1000 "), "1/10");
  assert.equal(parseExact("-.125"), "-1/8");
  assert.equal(parseExact("8."), "8/1");
  assert.equal(parseExact("-0/-012"), "0/1");
  assert.equal(parseExact("8/-12"), "-2/3");
  assert.equal(parseExact("9007199254740993.1"), "90071992547409931/10");
  assert.equal(compareExact("90071992547409931/10", "9007199254740993/1"), 1);
  assert.equal(compareExact("-2/3", "-1/2"), -1);
  assert.equal(compareExact("1/3", "1/3"), 0);
});

test("rejects malformed input and undefined fractions", () => {
  for (const input of ["", ".", "1 2", "1,234", "2e6", "NaN", Infinity, 0.5]) {
    assert.throws(() => parseExact(input), /Enter a number/);
  }
  assert.throws(() => parseExact("4/0"), /nonzero denominator/);
});

test("imports UTF-8 BOM, quoted cells, and alternate column order without rounding", () => {
  const rows = parseMeasurementsCsv('\uFEFF epsilon , "time", concentration\r\n 1/10 , "0.250" , 4.860\r\n0.50, 1/4, 4.87\r\n\r\n');
  assert.deepEqual(rows, [
    { time: "0.250", concentration: "4.860", epsilon: "1/10", included: true },
    { time: "1/4", concentration: "4.87", epsilon: "0.50", included: true },
  ]);
});

test("retains questionable field values for the user's review", () => {
  const [row] = parseMeasurementsCsv('time,concentration,epsilon\n1,"2,2","in\n""bounds"""\n');
  assert.deepEqual(row, { time: "1", concentration: "2,2", epsilon: 'in\n"bounds"', included: true });
  assert.deepEqual(validateMeasurements([row]).errors.map(({ field }) => field), [
    "concentration", "epsilon", "rows",
  ]);
});

test("describes malformed headers, inconsistent cells, and unterminated quotes", () => {
  assert.throws(() => parseMeasurementsCsv("time,concentration,SD"), /columns time, concentration, and epsilon/);
  assert.throws(() => parseMeasurementsCsv("time,time,epsilon"), /columns time, concentration, and epsilon/);
  assert.throws(() => parseMeasurementsCsv("time,concentration,epsilon\n1,2"), /line 2 has 2 cells/);
  assert.throws(() => parseMeasurementsCsv('time,concentration,epsilon\n1,2,"3'), /line 2 starts a quoted cell/);
  assert.throws(() => parseMeasurementsCsv('time,concentration,epsilon\n1,"2"x,3'), /line 2 needs a comma/);
  assert.throws(() => parseMeasurementsCsv('time,concentration,epsilon\n1,2"x,3'), /line 2 has a quote/);
});

test("counts exact distinct included times without dropping duplicate observations", () => {
  const rows = parseMeasurementsCsv("time,concentration,epsilon\n0.5,1,1/2\n1/2,2,1/2\n1,2,0\n2,3,0.5");
  rows[3].included = false;
  assert.deepEqual(validateMeasurements(rows), {
    errors: [
      { index: 2, field: "epsilon", message: "Enter a positive hard allowance." },
      { index: -1, field: "rows", message: "Include measurements at three or more distinct times." },
    ],
    distinctTimes: 2,
  });
  rows[2].epsilon = "0.1";
  rows[3].included = true;
  assert.deepEqual(validateMeasurements(rows), { errors: [], distinctTimes: 3 });
  assert.equal(rows.length, 4);
});

test("allows zero time and signed concentrations while reporting negative time", () => {
  const rows = parseMeasurementsCsv("time,concentration,epsilon\n0,-1,1\n1,3,1\n2,2,1\n-1,2,1");
  assert.deepEqual(validateMeasurements(rows), {
    errors: [{ index: 3, field: "time", message: "Enter a nonnegative elapsed time." }],
    distinctTimes: 3,
  });
});
