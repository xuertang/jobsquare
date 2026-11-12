import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";

export default defineToolPlugin({
  id: "jobops",
  name: "Jobops",
  description: "Add Jobops tools to OpenClaw.",
  tools: (tool) => [
    tool({
      name: "echo",
      description: "Echo input text.",
      parameters: Type.Object({
        input: Type.String({ description: "Text to echo." }),
      }),
      execute: async ({ input }) => ({ input }),
    }),
  ],
});
