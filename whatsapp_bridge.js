// BongaAI WhatsApp Bridge - FIXED crypto + fresh auth v2
const crypto = require('crypto')
global.crypto = crypto

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys')
const axios = require('axios')
const qrcode = require('qrcode-terminal')

const BRAIN_URL = process.env.BRAIN_URL || 'http://localhost:10000'
console.log(`[BongaAI] Brain URL: ${BRAIN_URL}`)

async function start() {
    // Changed folder to baileys_auth_v2 to force fresh QR (since free Render has no Shell)
    const { state, saveCreds } = await useMultiFileAuthState('baileys_auth_v2')
    const sock = makeWASocket({ 
        auth: state,
        printQRInTerminal: false,
        browser: ["BongaAI", "Chrome", "1.0"]
    })
    sock.ev.on('creds.update', saveCreds)
    sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
        if(qr) {
            try { require('fs').writeFileSync('baileys_auth_v2/qr.txt', qr); require('fs').writeFileSync('qr.txt', qr); } catch(e){}
            console.log(`QR saved - open https://bongaai-5.onrender.com/qr to scan - RAW: ${qr.substring(0,30)}...`)
            console.log("\n\n==== SCAN THIS QR IN WHATSAPP ====")
            qrcode.generate(qr, { small: true })
            console.log("WhatsApp > Linked Devices > Link a Device\n")
        }
        if(connection === 'close') {
            const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut
            console.log('Connection closed, reconnecting...', lastDisconnect?.error?.message?.slice(0,100))
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
