const fractionPattern = /^([+-]?\d+)\/([+-]?\d+)$/;
const decimalPattern = /^([+-]?)(\d*)(?:\.(\d*))?$/;

function greatestCommonDivisor(a, b) {
  a = a < 0n ? -a : a;
  while (b !== 0n) {
    [a, b] = [b, a % b];
  }
  return a;
}

export function parseExact(value) {
  const source = typeof value === "string" ? value.trim() : "";
  const fraction = fractionPattern.exec(source);
  let numerator;
  let denominator;

  if (fraction) {
    numerator = BigInt(fraction[1]);
    denominator = BigInt(fraction[2]);
  } else {
    const decimal = decimalPattern.exec(source);
    const whole = decimal?.[2] ?? "";
    const places = decimal?.[3] ?? "";
    if (!whole && !places) {
      throw new Error("Enter a number such as 2, 0.5, or 1/2.");
    }
    numerator = BigInt(decimal[1] + whole + places);
    denominator = 10n ** BigInt(places.length);
  }

  if (denominator === 0n) {
    throw new Error("Use a fraction with a nonzero denominator.");
  }
  if (denominator < 0n) {
    numerator = -numerator;
    denominator = -denominator;
  }
  const divisor = greatestCommonDivisor(numerator, denominator);
  return `${numerator / divisor}/${denominator / divisor}`;
}

export function compareExact(a, b) {
  const [aNumerator, aDenominator] = a.split("/").map(BigInt);
  const [bNumerator, bDenominator] = b.split("/").map(BigInt);
  const difference = aNumerator * bDenominator - bNumerator * aDenominator;
  if (difference < 0n) return -1;
  if (difference > 0n) return 1;
  return 0;
}

const measurementFields = ["time", "concentration", "epsilon"];

function readCsvRecords(text) {
  const source = text.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n");
  const records = [];
  let cursor = 0;
  let line = 1;

  function readField() {
    while (source[cursor] === " " || source[cursor] === "\t") cursor++;

    if (source[cursor] !== '"') {
      const start = cursor;
      while (cursor < source.length && source[cursor] !== "," && source[cursor] !== "\n") {
        if (source[cursor] === '"') {
          throw new Error(`CSV line ${line} has a quote inside an unquoted cell.`);
        }
        cursor++;
      }
      return source.slice(start, cursor).trim();
    }

    const startLine = line;
    cursor++;
    let value = "";
    while (cursor < source.length) {
      const character = source[cursor++];
      if (character === '"') {
        if (source[cursor] === '"') {
          value += '"';
          cursor++;
          continue;
        }
        while (source[cursor] === " " || source[cursor] === "\t") cursor++;
        if (cursor < source.length && source[cursor] !== "," && source[cursor] !== "\n") {
          throw new Error(`CSV line ${line} needs a comma or a new line after the quoted cell.`);
        }
        return value.trim();
      }
      if (character === "\n") line++;
      value += character;
    }
    throw new Error(`CSV line ${startLine} starts a quoted cell without a closing quote.`);
  }

  while (cursor < source.length) {
    const start = cursor;
    const startLine = line;
    const fields = [readField()];
    while (source[cursor] === ",") {
      cursor++;
      fields.push(readField());
    }
    if (source.slice(start, cursor).trim()) {
      records.push({ line: startLine, fields });
    }
    if (source[cursor] === "\n") {
      cursor++;
      line++;
    }
  }
  return records;
}

export function parseMeasurementsCsv(text) {
  const [header, ...records] = readCsvRecords(text);
  const columns = measurementFields.map((field) => header?.fields.indexOf(field) ?? -1);
  if (header?.fields.length !== measurementFields.length || columns.includes(-1)) {
    throw new Error("Use a CSV header with the columns time, concentration, and epsilon.");
  }

  return records.map(({ fields, line }) => {
    if (fields.length !== columns.length) {
      throw new Error(`CSV line ${line} has ${fields.length} cells. Supply one for each of time, concentration, and epsilon.`);
    }
    return {
      time: fields[columns[0]],
      concentration: fields[columns[1]],
      epsilon: fields[columns[2]],
      included: true,
    };
  });
}

// Limits of the server's dataset contract (apps/api/bean_api/contracts.py), checked here so a
// draft is refused before review instead of after it. The server remains the authority.
export const MAX_ROWS = 500;
export const MAX_SPELLING_LENGTH = 256;

export function isBlankRow(row) {
  return measurementFields.every((field) => !String(row[field] ?? "").trim());
}

export function validateMeasurements(rows) {
  const errors = [];
  const includedTimes = new Set();
  if (rows.length > MAX_ROWS) {
    errors.push({ index: -1, field: "rows", message: `Use at most ${MAX_ROWS} rows. This draft has ${rows.length}.` });
  }
  rows.forEach((row, index) => {
    if (isBlankRow(row)) {
      // An empty row is never silently dropped or guessed at. It is reported once, with the repair.
      errors.push({ index, field: "time", message: "This row is empty. Fill it in or remove it." });
      return;
    }
    for (const field of measurementFields) {
      try {
        if (String(row[field] ?? "").length > MAX_SPELLING_LENGTH) {
          throw new Error(`Use at most ${MAX_SPELLING_LENGTH} characters.`);
        }
        const value = parseExact(row[field]);
        if (field === "time") {
          if (compareExact(value, "0/1") < 0) {
            throw new Error("Enter a nonnegative elapsed time.");
          }
          if (row.included) includedTimes.add(value);
        }
        if (field === "epsilon" && compareExact(value, "0/1") <= 0) {
          throw new Error("Enter a positive hard allowance.");
        }
      } catch (error) {
        errors.push({ index, field, message: error.message });
      }
    }
  });

  if (includedTimes.size < 3) {
    errors.push({
      index: -1,
      field: "rows",
      message: "Include measurements at three or more distinct times.",
    });
  }
  return { errors, distinctTimes: includedTimes.size };
}
