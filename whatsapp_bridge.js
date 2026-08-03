// BongaAI WhatsApp Bridge - FIXED for Render (crypto bug)
const crypto = require('crypto')
global.crypto = crypto  // FIX: Baileys needs this

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys')
const axios = require('axios')
const qrcode = require('qrcode-terminal')

const BRAIN_URL = process.env.BRAIN_URL || 'http://localhost:10000'
console.log(`[BongaAI] Brain URL: ${BRAIN_URL}`)

async function start() {
    const { state, saveCreds } = await useMultiFileAuthState('baileys_auth')
    const sock = makeWASocket({ 
        auth: state,
        printQRInTerminal: false,
        browser: ["BongaAI", "Chrome", "1.0"]
    })
    sock.ev.on('creds.update', saveCreds)
    sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
        if(qr) {
            console.log("\n\n==== SCAN THIS QR IN WHATSAPP ====")
            qrcode.generate(qr, { small: true })
            console.log("WhatsApp > Linked Devices > Link a Device\n")
        }
        if(connection === 'close') {
            const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut
            console.log('Connection closed, reconnecting in 3s...', shouldReconnect ? '' : 'LOGGED OUT')
            if(shouldReconnect) setTimeout(start, 3000)
        }
        if(connection === 'open') console.log('✅ BongaAI is LIVE!')
    })
    sock.ev.on('messages.upsert', async ({ messages }) => {
        const msg = messages[0]
        if(!msg.message || msg.key.fromMe) return
        const phone = msg.key.remoteJid
        const text = msg.message.conversation || msg.message.extendedTextMessage?.text || msg.message.imageMessage?.caption || ""
        if(!text) return
        console.log(`IN: ${phone}: ${text}`)
        try {
            const res = await axios.post(`${BRAIN_URL}/message`, { phone, message: text }, { timeout: 20000 })
            await sock.sendMessage(phone, { text: res.data.reply })
        } catch(e) {
            console.log("Brain error", e.message)
            await sock.sendMessage(phone, { text: "Poa! I'm BongaAI 🤖 How can I help you leo?" })
        }
    })
}
start()
