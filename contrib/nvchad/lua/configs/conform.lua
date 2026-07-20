-- Formatters must be installed separately.
-- brew install ruff shfmt prettier
-- go install golang.org/x/tools/cmd/goimports@latest
-- terraform fmt is built into the terraform binary
-- Mason: stylua

local options = {
  formatters_by_ft = {
    lua = { "stylua" },

    python = { "ruff_format" },

    go = { "goimports", "gofmt" },

    sh   = { "shfmt" },
    bash = { "shfmt" },

    terraform          = { "terraform_fmt" },
    tf                 = { "terraform_fmt" },
    ["terraform-vars"] = { "terraform_fmt" },

    yaml     = { "prettier" },
    json     = { "prettier" },
    jsonc    = { "prettier" },
    markdown = { "prettier" },
  },

  -- Format on save is intentionally disabled.
  -- Use <leader>cf to format on demand (see mappings.lua).
  -- To enable per-session: require("conform").setup({ format_on_save = { timeout_ms = 1500, lsp_fallback = true } })
}

return options
