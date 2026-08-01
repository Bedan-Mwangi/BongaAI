// BongaAI WhatsApp Bridge - Render Ready
const { default: makeWASocket, useMultiFileAuthState } = require('@whiskeysockets/baileys')
const axios = require('axios')
const qrcode = require('qrcode-terminal')

const BRAIN_URL = process.env.BRAIN_URL || 'http://localhost:10000'
console.log(`BongaAI Brain URL: ${BRAIN_URL}`)

async function startBongaAI() {
    const { state, saveCreds } = await useMultiFileAuthState('baileys_auth')
    const sock = makeWASocket({ auth: state })

    sock.ev.on('creds.update', saveCreds)

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update
        
        if(qr) {
            console.log("\n\n==== BONGA AI QR CODE - SCAN ME ====")
            qrcode.generate(qr, { small: true })
            console.log("WhatsApp > Linked Devices > Link a Device")
            console.log("If on Render, check Logs - you have 30 seconds to scan!")
            console.log("=====================================\n")
        }

        if(connection === 'close') {
            console.log('Connection closed, reconnecting...')
            setTimeout(startBongaAI, 3000)
        } else if(connection === 'open') {
            console.log('✅ BongaAI is online! Bot Assistant: BongaAI is LIVE on Render!')
        }
    })

    sock.ev.on('messages.upsert', async ({ messages }) => {
        const msg = messages[0]
        if(!msg.message || msg.key.fromMe) return
        const phone = msg.key.remoteJid
        const text = msg.message.conversation || msg.message.extendedTextMessage?.text || msg.message.imageMessage?.caption || ""
        if(!text) return
        console.log(`Incoming ${phone}: ${text}`)
        try {
            const res = await axios.post(`${BRAIN_URL}/message`, { phone, message: text }, { timeout: 15000 })
            await sock.sendMessage(phone, { text: res.data.reply })
            console.log(`Replied: ${res.data.reply}`)
        } catch(e) {
            console.log("Brain error:", e.message)
            await sock.sendMessage(phone, { text: "Hey, I'm BongaAI 🤖 How can I help?" })
        }
    })
}

console.log("Starting Bot Assistant: BongaAI...")
startBongaAI()
