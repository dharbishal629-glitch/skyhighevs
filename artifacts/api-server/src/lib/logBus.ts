import { EventEmitter } from "events";
import crypto from "crypto";

interface LogEntry {
  id: string;
  level: string;
  message: string;
  timestamp: string;
  meta?: object;
}

class LogBus extends EventEmitter {
  private buffer: LogEntry[] = [];
  private readonly MAX_BUFFER = 500;

  emit(event: "log", entry: LogEntry): boolean;
  emit(event: string, ...args: unknown[]): boolean {
    return super.emit(event, ...args);
  }

  log(level: string, message: string, meta?: object) {
    const entry: LogEntry = {
      id: crypto.randomUUID(),
      level,
      message,
      timestamp: new Date().toISOString(),
      meta,
    };
    this.buffer.push(entry);
    if (this.buffer.length > this.MAX_BUFFER) {
      this.buffer.shift();
    }
    this.emit("log", entry);
  }

  info(message: string, meta?: object) {
    this.log("INFO", message, meta);
  }

  success(message: string, meta?: object) {
    this.log("SUCCESS", message, meta);
  }

  warn(message: string, meta?: object) {
    this.log("WARN", message, meta);
  }

  error(message: string, meta?: object) {
    this.log("ERROR", message, meta);
  }

  getBuffer(): LogEntry[] {
    return [...this.buffer];
  }
}

export const logBus = new LogBus();
export type { LogEntry };
