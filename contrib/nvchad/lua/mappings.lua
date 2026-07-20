require "nvchad.mappings"

local map = vim.keymap.set

-- ── General ──────────────────────────────────────────────────────────────
map("n", ";", ":", { desc = "CMD enter command mode" })
map("i", "jk", "<ESC>")
map("i", "kj", "<ESC>")
map("t", "<Esc><Esc>", "<C-\\><C-n>", { desc = "Exit terminal mode" })
map({ "n", "i", "v" }, "<C-s>", "<cmd>w<cr>", { desc = "Save file" })
-- Half-page scroll, then center cursor line (zz)
map("n", "<C-d>", "<C-d>zz", { desc = "Scroll down half page (center)" })
map("n", "<C-u>", "<C-u>zz", { desc = "Scroll up half page (center)" })

-- ── Formatting (on-demand only — no format-on-save) ──────────────────────
map("n", "<leader>cf", function()
  require("conform").format({ async = true, lsp_fallback = true })
end, { desc = "Format buffer" })

-- Toggle format-on-save for the current session (opt-in when you want it)
vim.g.format_on_save_enabled = false
map("n", "<leader>tf", function()
  vim.g.format_on_save_enabled = not vim.g.format_on_save_enabled
  if vim.g.format_on_save_enabled then
    require("conform").setup({ format_on_save = { timeout_ms = 1500, lsp_fallback = true } })
    vim.notify("Format on save: ON", vim.log.levels.INFO)
  else
    require("conform").setup({ format_on_save = nil })
    vim.notify("Format on save: OFF", vim.log.levels.INFO)
  end
end, { desc = "Toggle format on save" })

-- ── Trouble (diagnostics panel) ──────────────────────────────────────────
-- NvChad has ]d/[d for per-buffer nav; these give workspace-level views.
map("n", "<leader>xx", "<cmd>Trouble diagnostics toggle<cr>",                     { desc = "Workspace diagnostics" })
map("n", "<leader>xd", "<cmd>Trouble diagnostics toggle filter.buf=0<cr>",        { desc = "Document diagnostics" })
map("n", "<leader>xq", "<cmd>Trouble qflist toggle<cr>",                          { desc = "Quickfix list (Trouble)" })
map("n", "<leader>xl", "<cmd>Trouble loclist toggle<cr>",                         { desc = "Location list (Trouble)" })
map("n", "<leader>xs", "<cmd>Trouble lsp_document_symbols toggle<cr>",            { desc = "Document symbols (Trouble)" })

-- ── Git (Fugitive) ───────────────────────────────────────────────────────
-- gitsigns (NvChad built-in) handles inline hunks; fugitive handles operations.
map("n", "<leader>gg", "<cmd>Git<cr>",          { desc = "Git status (fugitive)" })
map("n", "<leader>gD", "<cmd>Gdiffsplit<cr>",   { desc = "Git diff split" })

-- ── Yazi ───────────────────────────────────────────────────────────────────
map("n", "<leader>y", function()
  require("yazi").toggle()
end, { desc = "Yazi (resume)" })
map("n", "<leader>yy", function()
  require("yazi").toggle()
end, { desc = "Yazi (resume)" })
map("n", "<leader>yw", function()
  require("yazi").yazi(nil, vim.fn.getcwd())
end, { desc = "Yazi cwd" })
map("n", "<leader>yp", function()
  local val = vim.fn.expand("%:p")
  vim.fn.setreg("+", val)
  vim.notify(val, vim.log.levels.INFO)
end, { desc = "Yank file path" })
map("n", "<leader>yn", function()
  local val = vim.fn.expand("%:t")
  vim.fn.setreg("+", val)
  vim.notify(val, vim.log.levels.INFO)
end, { desc = "Yank file name" })
map("n", "<leader>yd", function()
  local val = vim.fn.expand("%:p:h")
  vim.fn.setreg("+", val)
  vim.notify(val, vim.log.levels.INFO)
end, { desc = "Yank file dir" })
map("n", "<leader>yc", function()
  local val = vim.fn.getcwd()
  vim.fn.setreg("+", val)
  vim.notify(val, vim.log.levels.INFO)
end, { desc = "Yank cwd" })
