/** @type {import('next').NextConfig} */
const path = require('path')

const nextConfig = {
  transpilePackages: ['@shadergradient/react'],
  webpack: (config) => {
    config.resolve.alias['@shadergradient/react'] = path.resolve(__dirname, 'node_modules/@shadergradient/react/dist/index.mjs')
    return config
  }
}

module.exports = nextConfig
