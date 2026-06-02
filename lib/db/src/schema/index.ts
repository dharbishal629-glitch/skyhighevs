import { pgTable, text, serial, timestamp, integer, json } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const workersTable = pgTable("workers", {
  id: serial("id").primaryKey(),
  discordId: text("discord_id").notNull().unique(),
  discordUsername: text("discord_username").notNull(),
  workerKey: text("worker_key").notNull().unique(),
  status: text("status").notNull().default("VALID"),
  expiresAt: timestamp("expires_at"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

export const tokensTable = pgTable("tokens", {
  id: serial("id").primaryKey(),
  token: text("token").notNull().unique(),
  email: text("email"),
  accountPass: text("account_pass"),
  status: text("status").notNull().default("VALID"),
  workerId: integer("worker_id").references(() => workersTable.id),
  workerKey: text("worker_key"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  checkedAt: timestamp("checked_at"),
});

export const dailyStatsTable = pgTable("daily_stats", {
  id: serial("id").primaryKey(),
  workerId: integer("worker_id").references(() => workersTable.id).notNull(),
  date: text("date").notNull(),
  tokensGenerated: integer("tokens_generated").notNull().default(0),
  tokensValid: integer("tokens_valid").notNull().default(0),
  tokensLocked: integer("tokens_locked").notNull().default(0),
  tokensInvalid: integer("tokens_invalid").notNull().default(0),
});

export const toolConfigTable = pgTable("tool_config", {
  id: serial("id").primaryKey(),
  config: json("config").notNull().$type<Record<string, unknown>>().default({}),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

export const insertWorkerSchema = createInsertSchema(workersTable).omit({ id: true, createdAt: true, updatedAt: true });
export const insertTokenSchema = createInsertSchema(tokensTable).omit({ id: true, createdAt: true });
export const insertDailyStatSchema = createInsertSchema(dailyStatsTable).omit({ id: true });

export type Worker = typeof workersTable.$inferSelect;
export type InsertWorker = z.infer<typeof insertWorkerSchema>;
export type Token = typeof tokensTable.$inferSelect;
export type InsertToken = z.infer<typeof insertTokenSchema>;
export type DailyStat = typeof dailyStatsTable.$inferSelect;
export type InsertDailyStat = z.infer<typeof insertDailyStatSchema>;