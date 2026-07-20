return {
  "MeanderingProgrammer/render-markdown.nvim",
  ft = { "markdown" },
  dependencies = {
    "nvim-treesitter/nvim-treesitter",
    "nvim-tree/nvim-web-devicons", -- NvChad includes this
  },
  keys = {
    { "<leader>tm", "<cmd>RenderMarkdown toggle<cr>", ft = "markdown", desc = "Toggle markdown render" },
  },
  opts = {
    -- Render in normal and command mode; raw text in insert so editing is unaffected
    render_modes = { "n", "c" },

    heading = {
      -- Progressively smaller heading indicators
      icons = { "󰲡 ", "󰲣 ", "󰲥 ", "󰲧 ", "󰲩 ", "󰲫 " },
    },

    code = {
      -- Show the language label on fenced code blocks
      language_name = true,
      -- Full-width background on code blocks (cleaner than just the text)
      width = "full",
    },

    bullet = {
      -- Cycle through different bullet icons per nesting level
      icons = { "●", "○", "◆", "◇" },
    },

    checkbox = {
      unchecked = { icon = "󰄱 " },
      checked   = { icon = "󰱒 " },
    },
  },
}
