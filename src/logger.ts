import { appendFile } from "node:fs/promises";

/**
 * Logger 接口 - 支持依赖注入，便于测试时替换实现
 */
export interface Logger {
  /** 记录指令执行日志，包含时间戳、指令内容和执行结果 */
  log(command: string, result: string): Promise<void>;
}

/** 单条日志条目结构 */
export interface LogEntry {
  timestamp: string;  // ISO 8601 格式
  command: string;
  result: string;
}

/**
 * 将 LogEntry 格式化为单行 JSON 字符串（NDJSON 格式）
 */
export function formatLogEntry(entry: LogEntry): string {
  return JSON.stringify(entry);
}

/**
 * FileLogger - 将日志以 NDJSON 格式追加写入文件
 *
 * 每条日志包含：
 * - timestamp: ISO 8601 时间戳
 * - command: 指令内容
 * - result: 执行结果
 */
export class FileLogger implements Logger {
  constructor(private readonly logFilePath: string) {}

  async log(command: string, result: string): Promise<void> {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      command,
      result,
    };
    await appendFile(this.logFilePath, formatLogEntry(entry) + "\n", "utf-8");
  }
}
