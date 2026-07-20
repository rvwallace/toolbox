require("nvchad.configs.lspconfig").defaults()

-- Servers using default config (no custom settings needed)
local servers = {
  "html",
  "cssls",
  "terraformls",
  "pyright",
  "bashls",
  "gopls",
  "ansiblels",
  "sourcekit_lsp",
  "jsonls",
}

vim.lsp.enable(servers)

-- yamlls: enable schema validation via SchemaStore (b0o/SchemaStore.nvim).
-- Covers k8s, GitHub Actions, CircleCI, Renovate, docker-compose, and ~600 others.
-- ansiblels still handles Ansible files (it takes priority via its own filetypes).
vim.lsp.config("yamlls", {
  settings = {
    yaml = {
      schemaStore = {
        enable = false, -- use SchemaStore.nvim instead of yamlls's bundled store
        url    = "",
      },
      schemas  = require("schemastore").yaml.schemas(),
      validate = true,
      hover    = true,
      completion = true,
    },
  },
})
vim.lsp.enable("yamlls")
