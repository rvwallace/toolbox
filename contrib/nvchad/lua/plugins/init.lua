return {

  -- ── Formatting ──────────────────────────────────────────────────────────
  {
    "stevearc/conform.nvim",
    opts = require "configs.conform",
  },

  -- ── LSP ─────────────────────────────────────────────────────────────────
  {
    "neovim/nvim-lspconfig",
    -- SchemaStore must be available before configs.lspconfig runs (yamlls needs it)
    dependencies = { "b0o/SchemaStore.nvim" },
    config = function()
      require "configs.lspconfig"
    end,
  },

  -- ── Notifications / UI ──────────────────────────────────────────────────
  {
    "folke/noice.nvim",
    event = "VeryLazy",
    dependencies = {
      "MunifTanjim/nui.nvim",
      "rcarriga/nvim-notify", -- explicit dep; NvChad includes it but be safe
    },
    opts = {
      cmdline = {
        enabled = true,
        view    = "cmdline_popup",
      },
      messages = {
        enabled = true,
      },
      lsp = {
        -- Show LSP loading progress (mason installs, workspace indexing, etc.)
        progress = { enabled = true },
        -- Let NvChad handle hover and signature; noice taking over these
        -- causes double-popup issues with NvChad's own handlers.
        hover     = { enabled = false },
        signature = { enabled = false },
      },
      presets = {
        bottom_search        = true,  -- keep / search at the bottom statusline
        long_message_to_split = true, -- send long LSP/compiler output to a split
      },
      routes = {
        -- Suppress the "Nx lines, Ny bytes written" message on :w
        { filter = { event = "msg_show", find = "%d+L, %d+B" }, opts = { skip = true } },
        -- Suppress "No information available" hover noise
        { filter = { event = "msg_show", find = "^No information available" }, opts = { skip = true } },
      },
    },
  },

  -- ── Diagnostics panel ───────────────────────────────────────────────────
  -- Workspace-level diagnostics list. NvChad has ]d/[d for per-buffer navigation
  -- but no panel view. Trouble fills that gap cleanly.
  {
    "folke/trouble.nvim",
    cmd  = "Trouble",
    opts = {},
  },

  -- ── Editing comfort ──────────────────────────────────────────────────────
  -- Lightweight surround: ysa"( cs"' ds( etc.
  -- Essential for YAML/HCL/Go where you constantly rewrap strings and blocks.
  {
    "echasnovski/mini.surround",
    event = "BufReadPost",
    opts  = {},
  },

  -- ── Git operations ───────────────────────────────────────────────────────
  -- gitsigns (NvChad built-in) handles inline hunks and blame.
  -- Fugitive handles the operations: commit, push, log, diff, rebase.
  {
    "tpope/vim-fugitive",
    cmd = { "Git", "G", "Gdiffsplit", "Gread", "Gwrite" },
  },

}
